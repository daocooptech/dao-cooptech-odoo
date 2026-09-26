# -*- coding: utf-8 -*-
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Пороги постановки контракта на учёт, Инструкция Банка России от
# 16.08.2017 № 181-И: по сумме контракта целиком, а не по платежу.
# Разбор — `Матчасть/legal-counsel/2026-09-23 — Путь к международным
# расчётам, бирже и ЦФА`, раздел 1.1, шаг 3.
DOCS_FREE_LIMIT = 1_000_000          # до 1 млн ₽ — только код вида операции
IMPORT_THRESHOLD = 3_000_000         # импорт, работы и услуги от нерезидента
EXPORT_THRESHOLD = 10_000_000        # экспорт, работы и услуги нерезиденту

DIRECTIONS = [
    ('export_goods', 'Экспорт товаров'),
    ('import_goods', 'Импорт товаров'),
    ('export_services', 'Экспорт работ и услуг'),
    ('import_services', 'Импорт работ и услуг'),
]

SETTLEMENTS = [
    ('transfer', 'Перевод через уполномоченный банк'),
    ('lc', 'Безотзывный документарный аккредитив'),
    ('cfa', 'ЦФА по внешнеторговому договору'),
    ('barter', 'Встречная поставка'),
]

INCOTERMS = [(code, code) for code in (
    'EXW', 'FCA', 'CPT', 'CIP', 'DAP', 'DPU', 'DDP', 'FAS', 'FOB', 'CFR', 'CIF')]


def _flag(code):
    """Флаг страны из двух букв кода — символами регионального индикатора."""
    code = (code or '').upper()
    if len(code) != 2 or not code.isalpha():
        return ''
    return ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in code)


def _rub(amount):
    return '{:,.0f}'.format(amount or 0).replace(',', ' ') + ' ₽'


class CoopTradeContract(models.Model):
    """Внешнеторговый контракт — от заключения до снятия с учёта.

    Решение 392: запрещена оплата, а не инструмент; расчёты резидента с
    нерезидентом платформа обязана уметь. Решение 410: международный
    контур расчётов — безотзывный документарный аккредитив рядом с
    номинальным счётом для внутренних сделок.

    Платформа здесь — витрина и помощник, а не сторона и не агент
    (разбор юриста, 1.2): контракт заключают стороны между собой и
    платят через свои банки. Поэтому здесь нет ни кнопки «оплатить», ни
    чужих денег — есть шесть полей, без которых банк контракт не примет,
    порог постановки на учёт, способ расчёта и ведомость «отгружено —
    оплачено — осталось» со сроком репатриации.
    """
    _name = 'coop.trade.contract'
    _description = 'Внешнеторговый контракт'
    _inherit = ['mail.thread']
    _order = 'signed_on desc, id desc'
    _rec_name = 'display_name'

    number = fields.Char(string='Номер', readonly=True, copy=False, index=True)
    display_name = fields.Char(compute='_compute_display_name', store=True)
    name = fields.Char(string='Предмет кратко', required=True, tracking=True)
    direction = fields.Selection(
        DIRECTIONS, string='Что и куда', required=True, default='export_goods',
        index=True, tracking=True)
    is_goods = fields.Boolean(compute='_compute_is_goods')
    is_export = fields.Boolean(compute='_compute_is_goods')

    # ── 1. Стороны с точными реквизитами и страной ────────────────────
    resident_id = fields.Many2one(
        'res.partner', string='Российская сторона', required=True, index=True,
        tracking=True, default=lambda self: self.env.user.partner_id)
    foreign_name = fields.Char(string='Иностранная сторона', required=True, tracking=True)
    foreign_country_id = fields.Many2one(
        'res.country', string='Страна контрагента', required=True, index=True)
    foreign_partner_id = fields.Many2one(
        'res.partner', string='Контрагент на платформе',
        help='Если иностранная сторона — тоже участник платформы.')
    foreign_details = fields.Text(
        string='Реквизиты контрагента',
        help='Полное наименование, регистрационный номер, адрес, банк.')
    flag = fields.Char(compute='_compute_flag')
    # Флаг — картинкой движка, а не символами: на Windows флаги-эмодзи
    # рисуются двумя буквами («AM»).
    flag_url = fields.Char(related='foreign_country_id.image_url', string='Флаг')
    city = fields.Char(related='resident_id.city', string='Город', store=True)

    # ── 2. Предмет ─────────────────────────────────────────────────────
    subject = fields.Text(
        string='Предмет с количеством и характеристиками',
        help='Подтверждающие документы должны сойтись с контрактом, '
             'иначе расхождение в ведомости банковского контроля.')

    # ── 3. Валюта цены и валюта платежа — отдельно ────────────────────
    price_currency_id = fields.Many2one(
        'res.currency', string='Валюта цены', required=True,
        default=lambda self: self.env.ref('base.RUB', raise_if_not_found=False))
    payment_currency_id = fields.Many2one(
        'res.currency', string='Валюта платежа', required=True,
        default=lambda self: self.env.ref('base.RUB', raise_if_not_found=False))
    amount = fields.Monetary(
        string='Сумма контракта', currency_field='price_currency_id', tracking=True)
    rub_currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.ref('base.RUB', raise_if_not_found=False))
    amount_rub = fields.Monetary(
        string='Сумма в рублях', currency_field='rub_currency_id',
        help='По курсу Банка России на дату заключения. От неё считается '
             'порог постановки на учёт. Курс платформа не подставляет: на '
             'дату платежа его определяет банк.')

    # ── 4. Сроки исполнения и оплаты ──────────────────────────────────
    signed_on = fields.Date(string='Заключён', tracking=True)
    performance_date = fields.Date(
        string='Срок исполнения обязательств', tracking=True,
        help='Отгрузка товара, выполнение работ, оказание услуг.')
    payment_due = fields.Date(
        string='Срок оплаты', tracking=True,
        help='От него считается репатриация выручки (ст. 19 ФЗ-173).')

    # ── 5. Применимое право и споры ───────────────────────────────────
    governing_law = fields.Selection([
        ('ru', 'Право Российской Федерации'),
        ('counterparty', 'Право страны контрагента'),
        ('third', 'Право третьей страны'),
    ], string='Применимое право')
    dispute_forum = fields.Selection([
        ('mkas', 'МКАС при ТПП РФ'),
        ('ru_court', 'Арбитражный суд РФ'),
        ('foreign_arbitration', 'Иностранный арбитраж'),
    ], string='Где разрешаются споры')

    # ── 6. Условия поставки и переход рисков ──────────────────────────
    incoterms = fields.Selection(INCOTERMS, string='Инкотермс 2020')
    incoterms_place = fields.Char(string='Место по Инкотермс')

    # ── Постановка на учёт (181-И) ─────────────────────────────────────
    registration = fields.Selection([
        ('code', 'Только код вида операции'),
        ('request', 'Документы — по запросу банка'),
        ('unk', 'Постановка на учёт, УНК'),
    ], string='Что требует банк', compute='_compute_registration', store=True)
    threshold = fields.Monetary(
        string='Порог постановки на учёт', currency_field='rub_currency_id',
        compute='_compute_registration', store=True)
    bank_name = fields.Char(string='Уполномоченный банк')
    unk = fields.Char(string='УНК', tracking=True,
                      help='Уникальный номер контракта — присваивается банком '
                           'до первого платежа или первой отгрузки.')
    unk_on = fields.Date(string='Поставлен на учёт')

    # ── Расчёт ────────────────────────────────────────────────────────
    settlement = fields.Selection(
        SETTLEMENTS, string='Способ расчёта', required=True, default='transfer',
        tracking=True)
    lc_issuing_bank = fields.Char(string='Банк-эмитент')
    lc_advising_bank = fields.Char(string='Авизующий банк')
    lc_amount = fields.Monetary(string='Сумма аккредитива', currency_field='payment_currency_id')
    lc_expiry = fields.Date(string='Аккредитив действует до')
    lc_documents = fields.Text(
        string='Документы для раскрытия',
        help='Против каких документов банк платит: коносамент, инвойс, '
             'сертификат происхождения, упаковочный лист.')
    lc_state = fields.Selection([
        ('requested', 'Заявление подано'),
        ('opened', 'Открыт'),
        ('confirmed', 'Подтверждён'),
        ('documents', 'Документы представлены'),
        ('paid', 'Исполнен'),
        ('expired', 'Истёк'),
    ], string='Аккредитив', tracking=True)
    cfa_operator_id = fields.Many2one('coop.cfa.operator', string='Оператор ИС')
    cfa_step = fields.Selection([
        ('issue', '1. Выпуск ЦФА у оператора'),
        ('access', '2. Нерезидент получил доступ к ИС'),
        ('transfer', '3. ЦФА переданы нерезиденту'),
        ('redeem', '4. ЦФА погашены деньгами'),
    ], string='Шаг сценария ЦФА', tracking=True)

    # ── Исполнение ─────────────────────────────────────────────────────
    document_ids = fields.One2many(
        'coop.trade.document', 'contract_id', string='Подтверждающие документы')
    payment_ids = fields.One2many(
        'coop.trade.payment', 'contract_id', string='Платежи')
    shipped_total = fields.Monetary(
        string='Исполнено', currency_field='price_currency_id',
        compute='_compute_ledger', store=True)
    paid_total = fields.Monetary(
        string='Оплачено', currency_field='price_currency_id',
        compute='_compute_ledger', store=True)
    balance = fields.Monetary(
        string='Разница', currency_field='price_currency_id',
        compute='_compute_ledger', store=True,
        help='Исполнено минус оплачено: плюс — ждём денег, минус — аванс '
             'без исполнения.')
    repatriation_state = fields.Selection([
        ('none', 'Не требуется'),
        ('ok', 'В срок'),
        ('soon', 'Срок близко'),
        ('late', 'Срок прошёл'),
        ('done', 'Выручка получена'),
    ], string='Репатриация', compute='_compute_repatriation')

    state = fields.Selection([
        ('draft', 'Проект'),
        ('signed', 'Заключён'),
        ('registered', 'На учёте в банке'),
        ('performing', 'Исполняется'),
        ('done', 'Исполнен'),
        ('closed', 'Снят с учёта'),
        ('cancelled', 'Расторгнут'),
    ], string='Состояние', default='draft', required=True, index=True, tracking=True)

    checklist_html = fields.Html(
        string='Шесть полей', compute='_compute_checklist', sanitize=False)
    missing_count = fields.Integer(compute='_compute_checklist')
    warnings_html = fields.Html(compute='_compute_checklist', sanitize=False)
    icon = fields.Char(compute='_compute_flag')
    amount_label = fields.Char(compute='_compute_labels')
    settlement_short = fields.Char(compute='_compute_labels')
    registration_label = fields.Char(compute='_compute_labels')
    is_mine = fields.Boolean(compute='_compute_is_mine', search='_search_is_mine')

    # ── Вычисления ─────────────────────────────────────────────────────

    @api.depends('number', 'name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = ('%s · %s' % (record.number, record.name)
                                   if record.number else record.name or '')

    @api.depends('direction')
    def _compute_is_goods(self):
        for record in self:
            record.is_goods = (record.direction or '').endswith('_goods')
            record.is_export = (record.direction or '').startswith('export')

    @api.depends('foreign_country_id', 'direction')
    def _compute_flag(self):
        for record in self:
            record.flag = _flag(record.foreign_country_id.code)
            record.icon = '📤' if (record.direction or '').startswith('export') else '📥'

    @api.depends('direction', 'amount_rub')
    def _compute_registration(self):
        for record in self:
            export = (record.direction or '').startswith('export')
            record.threshold = EXPORT_THRESHOLD if export else IMPORT_THRESHOLD
            amount = record.amount_rub or 0
            if amount < DOCS_FREE_LIMIT:
                record.registration = 'code'
            elif amount < record.threshold:
                record.registration = 'request'
            else:
                record.registration = 'unk'

    @api.depends('document_ids.amount', 'payment_ids.amount')
    def _compute_ledger(self):
        for record in self:
            record.shipped_total = sum(record.document_ids.filtered(
                lambda d: d.kind != 'other').mapped('amount'))
            record.paid_total = sum(record.payment_ids.mapped('amount'))
            record.balance = record.shipped_total - record.paid_total

    @api.depends('payment_due', 'direction', 'balance', 'shipped_total', 'state')
    def _compute_repatriation(self):
        today = fields.Date.context_today(self)
        for record in self:
            if not (record.direction or '').startswith('export') \
                    or record.state in ('draft', 'cancelled'):
                record.repatriation_state = 'none'
            elif record.shipped_total and record.balance <= 0:
                record.repatriation_state = 'done'
            elif not record.payment_due:
                record.repatriation_state = 'ok'
            elif record.payment_due < today:
                record.repatriation_state = 'late'
            elif record.payment_due - today <= timedelta(days=14):
                record.repatriation_state = 'soon'
            else:
                record.repatriation_state = 'ok'

    def _compute_labels(self):
        settlement = dict(self._fields['settlement'].selection)
        short = {'transfer': 'Перевод', 'lc': 'Аккредитив', 'cfa': 'ЦФА',
                 'barter': 'Встречная поставка'}
        for record in self:
            record.amount_label = '{:,.0f} {}'.format(
                record.amount or 0,
                record.price_currency_id.symbol or record.price_currency_id.name or '',
            ).replace(',', ' ')
            record.settlement_short = short.get(record.settlement, settlement.get(record.settlement, ''))
            if record.registration == 'unk':
                record.registration_label = ('УНК %s' % record.unk) if record.unk else 'Нужен УНК'
            elif record.registration == 'request':
                record.registration_label = 'Документы по запросу'
            else:
                record.registration_label = 'Без постановки на учёт'

    def _compute_is_mine(self):
        mine = self.env.user.coop_actor_partner_ids
        for record in self:
            record.is_mine = record.resident_id in mine or record.foreign_partner_id in mine

    def _search_is_mine(self, operator, value):
        ids = self.env.user.coop_actor_partner_ids.ids
        domain = ['|', ('resident_id', 'in', ids), ('foreign_partner_id', 'in', ids)]
        if operator != 'in':  # Odoo 19: признак — оператором in
            return NotImplemented
        return domain

    @api.depends('resident_id', 'foreign_name', 'foreign_country_id', 'foreign_details', 'subject',
                 'price_currency_id', 'payment_currency_id', 'performance_date',
                 'payment_due', 'governing_law', 'dispute_forum', 'incoterms',
                 'direction', 'registration', 'unk', 'settlement', 'amount_rub')
    def _compute_checklist(self):
        for record in self:
            goods = (record.direction or '').endswith('_goods')
            items = [
                (_('Стороны с реквизитами и страной'),
                 bool(record.resident_id and record.foreign_name
                      and record.foreign_country_id and record.foreign_details),
                 _('банк откажет в постановке на учёт')),
                (_('Предмет с количеством и характеристиками'), bool(record.subject),
                 _('документы не сойдутся с контрактом в ведомости банка')),
                (_('Валюта цены и валюта платежа — отдельно'),
                 bool(record.price_currency_id and record.payment_currency_id),
                 _('спор о сумме при движении курса')),
                (_('Сроки исполнения и оплаты'),
                 bool(record.performance_date and record.payment_due),
                 _('от срока оплаты считается репатриация; штраф по ст. 15.25 КоАП')),
                (_('Применимое право и порядок споров'),
                 bool(record.governing_law and record.dispute_forum),
                 _('спор в суде страны контрагента по незнакомому праву')),
                (_('Условия поставки (Инкотермс) и переход рисков'),
                 bool(record.incoterms) or not goods,
                 _('налоговый спор о периоде реализации')),
            ]
            rows = []
            missing = 0
            for label, ok, risk in items:
                if not ok:
                    missing += 1
                rows.append(Markup(
                    '<li class="o_coop_trade_check %s"><span class="o_coop_trade_mark">%s</span>'
                    '<span>%s%s</span></li>') % (
                    'o_coop_trade_ok' if ok else 'o_coop_trade_miss',
                    '✓' if ok else '✗', label,
                    Markup('') if ok else Markup(' — <em>%s</em>') % risk))
            record.checklist_html = Markup('<ul class="o_coop_trade_checklist">%s</ul>') % Markup('').join(rows)
            record.missing_count = missing

            warnings = []
            if record.dispute_forum == 'foreign_arbitration':
                warnings.append(_(
                    'Иностранный арбитраж не гарантирует рассмотрения спора: '
                    'ст. 248.1 АПК отдаёт споры с лицами под ограничительными '
                    'мерами арбитражным судам РФ. Безопаснее МКАС при ТПП РФ.'))
            if record.registration == 'unk' and not record.unk and record.state not in ('draft', 'cancelled'):
                warnings.append(_(
                    'Сумма выше порога — контракт ставится на учёт до первого '
                    'платежа или отгрузки. Опоздание — ч. 6 ст. 15.25 КоАП, '
                    'для юрлица 40–50 тыс. ₽.'))
            if record.settlement == 'barter':
                warnings.append(_(
                    'Встречная поставка с нерезидентом — отдельный режим '
                    '(ст. 44 ФЗ-164): зачёт вместо денег допускается только в '
                    'случаях ч. 2 ст. 19 ФЗ-173. Не кнопка — согласовать с '
                    'банком заранее.'))
            record.warnings_html = Markup('').join(
                Markup('<div class="alert alert-warning mb-2">%s</div>') % w for w in warnings)

    # ── Жизненный цикл ─────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records.filtered(lambda r: not r.number):
            record.number = 'ВЭД-%s-%04d' % (
                (record.signed_on or fields.Date.context_today(record)).year, record.id)
        return records

    def action_sign(self):
        for record in self:
            if record.missing_count:
                raise UserError(_(
                    'Не заполнено обязательных полей: %(count)s. Без них банк '
                    'контракт не примет — см. «Шесть полей».', count=record.missing_count))
            record.write({'state': 'signed',
                          'signed_on': record.signed_on or fields.Date.context_today(record)})

    def action_register(self):
        for record in self:
            if record.registration == 'unk' and not record.unk:
                raise UserError(_('Впишите УНК, присвоенный банком.'))
            record.write({'state': 'registered' if record.registration == 'unk' else 'performing',
                          'unk_on': record.unk_on or fields.Date.context_today(record)})

    def action_perform(self):
        self.write({'state': 'performing'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})

    # ── Панель фильтров каталога ───────────────────────────────────────

    def _coop_catalog_filters(self, domain):
        def choice(name):
            return [{'value': code, 'label': label}
                    for code, label in self._fields[name].selection]

        countries = self.env['res.country'].sudo().browse(
            self.sudo().search([]).foreign_country_id.ids).sorted('name')
        currencies = self.env['res.currency'].sudo().browse(
            self.sudo().search([]).payment_currency_id.ids).sorted('name')
        return [
            {'code': 'direction', 'label': 'Что и куда', 'widget': 'select',
             'field': 'direction', 'placeholder': 'Любое', 'options': choice('direction')},
            {'code': 'country', 'label': 'Страна контрагента', 'widget': 'select',
             'field': 'foreign_country_id', 'placeholder': 'Любая',
             'options': [{'value': c.id, 'label': c.name}
                         for c in countries]},
            {'code': 'currency', 'label': 'Валюта платежа', 'widget': 'select',
             'field': 'payment_currency_id', 'placeholder': 'Любая',
             'options': [{'value': c.id, 'label': c.name} for c in currencies]},
            {'code': 'settlement', 'label': 'Способ расчёта', 'widget': 'select',
             'field': 'settlement', 'placeholder': 'Любой', 'options': choice('settlement')},
            {'code': 'state', 'label': 'Состояние', 'widget': 'select',
             'field': 'state', 'placeholder': 'Любое', 'options': choice('state')},
            {'code': 'amount_rub', 'label': 'Сумма в рублях',
             'hint': 'Порог учёта: импорт — от 3 млн ₽, экспорт — от 10 млн ₽.',
             'widget': 'range', 'field': 'amount_rub'},
            {'code': 'quick', 'label': 'Быстрые фильтры', 'widget': 'quick', 'options': [
                {'value': 'unk', 'label': '🏦 Нужен УНК',
                 'domain': [('registration', '=', 'unk'), ('unk', '=', False)]},
                {'value': 'lc', 'label': '📜 Аккредитив',
                 'domain': [('settlement', '=', 'lc')]},
                {'value': 'cfa', 'label': '🔗 ЦФА', 'domain': [('settlement', '=', 'cfa')]},
                {'value': 'open', 'label': '⏳ Не исполнены',
                 'domain': [('state', 'in', ('signed', 'registered', 'performing'))]},
            ]},
        ]


class CoopTradeDocument(models.Model):
    """Подтверждающий документ: отгрузка, акт, инвойс.

    Справка о подтверждающих документах подаётся в банк в течение 15
    рабочих дней после месяца, в котором документ оформлен (гл. 8 181-И).
    """
    _name = 'coop.trade.document'
    _description = 'Подтверждающий документ'
    _order = 'date desc, id desc'

    contract_id = fields.Many2one('coop.trade.contract', required=True, index=True,
                                  ondelete='cascade')
    date = fields.Date(string='Дата документа', required=True)
    kind = fields.Selection([
        ('declaration', 'Декларация на товары'),
        ('transport', 'Транспортный документ'),
        ('act', 'Акт выполненных работ'),
        ('invoice', 'Инвойс'),
        ('other', 'Прочее'),
    ], string='Документ', required=True, default='invoice')
    number = fields.Char(string='Номер')
    currency_id = fields.Many2one(related='contract_id.price_currency_id')
    amount = fields.Monetary(string='Сумма', currency_field='currency_id')
    spd_due = fields.Date(string='СПД — до', compute='_compute_spd_due', store=True,
                          help='Справка о подтверждающих документах: 15 рабочих '
                               'дней после месяца документа.')

    @api.depends('date')
    def _compute_spd_due(self):
        for doc in self:
            if not doc.date:
                doc.spd_due = False
                continue
            day = doc.date + relativedelta(day=31)
            left = 15
            while left:
                day += timedelta(days=1)
                if day.weekday() < 5:
                    left -= 1
            doc.spd_due = day


class CoopTradePayment(models.Model):
    _name = 'coop.trade.payment'
    _description = 'Платёж по внешнеторговому контракту'
    _order = 'date desc, id desc'

    contract_id = fields.Many2one('coop.trade.contract', required=True, index=True,
                                  ondelete='cascade')
    date = fields.Date(string='Дата', required=True)
    currency_id = fields.Many2one(related='contract_id.price_currency_id')
    amount = fields.Monetary(string='Сумма в валюте цены', currency_field='currency_id')
    note = fields.Char(string='Назначение')


class CoopTradeCalculator(models.TransientModel):
    """Калькулятор порога постановки на учёт — без заведения контракта."""
    _name = 'coop.trade.calculator'
    _description = 'Калькулятор порога 181-И'

    direction = fields.Selection(DIRECTIONS, string='Что и куда', required=True,
                                 default='import_goods')
    rub_currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.ref('base.RUB', raise_if_not_found=False))
    amount_rub = fields.Monetary(string='Сумма контракта в рублях',
                                 currency_field='rub_currency_id')
    result_html = fields.Html(compute='_compute_result', sanitize=False)

    @api.depends('direction', 'amount_rub')
    def _compute_result(self):
        for calc in self:
            export = (calc.direction or '').startswith('export')
            threshold = EXPORT_THRESHOLD if export else IMPORT_THRESHOLD
            amount = calc.amount_rub or 0
            if amount < DOCS_FREE_LIMIT:
                head, text = _('Постановка на учёт не нужна'), _(
                    'До 1 млн ₽ — только код вида операции в платёжном поручении; '
                    'документы в банк не представляются (п. 2.7 181-И).')
            elif amount < threshold:
                head, text = _('Документы — по запросу банка'), _(
                    'От 1 млн ₽ до порога %(t)s контракт на учёт не ставится, '
                    'но банк вправе запросить документы — это день-два.', t=_rub(threshold))
            else:
                head, text = _('Нужна постановка на учёт — УНК'), _(
                    'От %(t)s контракт ставится на учёт в уполномоченном банке до '
                    'первого платежа или первой отгрузки; банк присваивает УНК за '
                    '1 рабочий день. Сумма считается по контракту целиком, включая '
                    'рамочный.', t=_rub(threshold))
            calc.result_html = Markup(
                '<div class="o_coop_trade_calc"><b>%s</b><p>%s</p>'
                '<p class="text-muted">Порог для «%s» — %s.</p></div>') % (
                head, text, dict(DIRECTIONS)[calc.direction], _rub(threshold))
