# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopCfaOperator(models.Model):
    """Оператор информационной системы из реестра Банка России.

    Выпуск и обращение цифровых финансовых активов возможны только в
    информационной системе оператора, включённого в реестр ЦБ. Это не
    формальность, которую обходят договором: у выпуска вне такой системы
    нет ни признания, ни защиты, а у выпустившего — проблемы вместо
    привлечённых денег.

    Поэтому платформа сама ЦФА не выпускает и не собирается. Она делает
    то, что действительно нужно кооперативу: собирает параметры будущего
    выпуска, готовит документы и передаёт их оператору, а потом
    показывает результат рядом с паями и токенами. Выпуск и оборот
    остаются у оператора — это исполнение требования, а не его обход.

    Справочник ведётся вручную и намеренно: реестр ЦБ меняется, тянуть
    его автоматически неоткуда, а показывать участнику устаревший список
    операторов хуже, чем короткий.
    """
    _name = 'coop.cfa.operator'
    _description = 'Оператор ЦФА из реестра ЦБ'
    _order = 'sequence, name'

    name = fields.Char(string='Оператор', required=True)
    sequence = fields.Integer(string='Порядок', default=10)
    partner_id = fields.Many2one('res.partner', string='Юридическое лицо')
    inn = fields.Char(string='ИНН')
    registry_number = fields.Char(
        string='Номер в реестре ЦБ',
        help='Запись в реестре операторов информационных систем.')
    registered_on = fields.Date(string='Включён в реестр')
    website = fields.Char(string='Сайт')

    issues_what = fields.Char(
        string='Что выпускает',
        help='«Денежные требования, права участия в непубличном АО» — '
             'у операторов разный перечень, и это первое, что нужно '
             'сравнивать.')
    fee_note = fields.Char(
        string='Комиссии',
        help='Как берёт оператор: процент от выпуска, фиксированная плата, '
             'плата за сделку.')
    unqualified_limit = fields.Monetary(
        string='Лимит для неквалифицированных', currency_field='currency_id',
        help='Сколько в год вправе вложить неквалифицированный инвестор. '
             'Устанавливается регулированием, а не оператором.')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)

    note = fields.Text(string='Примечание')
    active = fields.Boolean(string='Действует', default=True)

    issue_ids = fields.One2many('coop.cfa.issue', 'operator_id', string='Заявки')


class CoopCfaIssue(models.Model):
    """Заявка на выпуск ЦФА через оператора.

    Здесь заполняется всё, что оператор всё равно спросит: кто выпускает,
    что удостоверяет актив, на какую сумму, на какой срок и чем
    обеспечено. Платформа собирает это в одном месте и передаёт — а
    решение о выпуске принимает оператор, и отказ его тоже.

    Состояния честные: «передана оператору» не означает «выпущено».
    Показывать участнику выпуск, которого нет, — худшее, что может
    сделать витрина.
    """
    _name = 'coop.cfa.issue'
    _description = 'Заявка на выпуск ЦФА'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'
    _rec_name = 'display_name'

    display_name = fields.Char(compute='_compute_display_name', store=True)

    issuer_id = fields.Many2one(
        'res.partner', string='Эмитент', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(),
        help='Кто выпускает. Обязательства по выпуску несёт он, а не '
             'платформа и не оператор.')
    operator_id = fields.Many2one(
        'coop.cfa.operator', string='Оператор', index=True,
        help='Через кого идёт выпуск. Пока не выбран — заявка черновик.')

    name = fields.Char(string='Название выпуска', required=True)
    rights_kind = fields.Selection([
        ('money_claim', 'Денежное требование'),
        ('share_rights', 'Права участия в капитале'),
        ('security_rights', 'Права по ценным бумагам'),
        ('goods_claim', 'Требование передать вещь'),
    ], string='Что удостоверяет', required=True, default='money_claim',
        help='Перечень прав у операторов разный — с этого и начинается '
             'выбор оператора.')
    description = fields.Html(string='Описание выпуска')

    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)
    amount = fields.Monetary(
        string='Объём выпуска', currency_field='currency_id', required=True)
    unit_count = fields.Integer(string='Количество единиц')
    unit_price = fields.Monetary(
        string='Цена единицы', currency_field='currency_id',
        compute='_compute_unit_price', store=True)
    maturity_date = fields.Date(
        string='Срок погашения',
        help='Когда эмитент обязан исполнить удостоверенное право.')

    collateral = fields.Char(
        string='Обеспечение',
        help='Залог, поручительство, нематериальный актив. Пусто — выпуск '
             'ничем не обеспечен, и покупатель должен видеть это прямо.')
    intangible_id = fields.Many2one(
        'coop.intangible', string='Обеспечен активом',
        help='Нематериальный актив из реестра, если обеспечение — он.')

    state = fields.Selection([
        ('draft', 'Черновик'),
        ('submitted', 'Передана оператору'),
        ('accepted', 'Принята оператором'),
        ('issued', 'Выпущено'),
        ('rejected', 'Отказ оператора'),
        ('redeemed', 'Погашено'),
    ], string='Состояние', default='draft', required=True, index=True, tracking=True)

    submitted_on = fields.Date(string='Передана', readonly=True)
    issued_on = fields.Date(string='Выпущено', readonly=True)
    external_reference = fields.Char(
        string='Номер у оператора', readonly=True, copy=False,
        help='Идентификатор выпуска в информационной системе оператора. '
             'По нему сверяются, когда данные расходятся.')
    rejection_reason = fields.Char(string='Причина отказа', readonly=True)

    import_key = fields.Char(string='Ключ источника', index=True, copy=False)


    is_mine = fields.Boolean(
        string='Моё', compute='_compute_is_mine', search='_search_is_mine',
        help='Своё — то, что принадлежит участнику или организации, счета '
             'которой он ведёт.')

    def _my_partners(self):
        """Партнёры, от чьего лица действует пользователь.

        Не один партнёр, а набор: участник ведёт счета своей организации
        и действует от её имени. Тот же набор используют правила
        видимости — иначе «моё» и «что мне видно» разошлись бы.
        """
        return self.env.user.coop_treasury_partner_ids

    @api.depends_context('uid')
    def _compute_is_mine(self):
        mine = self._my_partners()
        for record in self:
            record.is_mine = record.issuer_id in mine

    def _search_is_mine(self, operator, value):
        # Отбор идёт на сервере, а не выражением в самом действии:
        # клиентский разборщик выражений не понимает обращений к полям
        # пользователя, и вкладка «моё» не открывалась вовсе.
        # Odoo приводит «= True» к «in {True}» ещё до вызова поиска и
        # передаёт при этом свой набор, а не список. Поэтому значение
        # разбирается как последовательность, а не сверяется с типом:
        # иначе вкладка «моё» падала с ошибкой прямо при открытии.
        if isinstance(value, bool):
            wanted = value
        else:
            items = list(value)
            if len(items) != 1 or not isinstance(items[0], bool):
                raise ValueError('Поддерживается только «моё: да» или «моё: нет».')
            wanted = items[0]
        if operator in ('=', 'in'):
            positive = wanted
        elif operator in ('!=', 'not in'):
            positive = not wanted
        else:
            raise ValueError('Поддерживается только «моё: да» или «моё: нет».')
        return [('issuer_id', 'in' if positive else 'not in',
                 self._my_partners().ids)]

    @api.depends('name', 'issuer_id.name', 'amount')
    def _compute_display_name(self):
        for record in self:
            record.display_name = '%s — %s' % (
                record.name or _('Выпуск'), record.issuer_id.name or '')

    @api.depends('amount', 'unit_count')
    def _compute_unit_price(self):
        for record in self:
            record.unit_price = (
                record.amount / record.unit_count if record.unit_count else 0.0)

    def action_submit(self):
        """Передать заявку оператору.

        Оператор обязателен именно здесь: пока его нет, заявка — заготовка
        в столе. И проверка эмитента: выпускать вправе тот, чью личность
        подтвердили, — оператор всё равно проверит, но лучше узнать об
        этом до подачи, чем после отказа.
        """
        for record in self:
            if not record.operator_id:
                raise UserError(_(
                    'Выберите оператора из реестра ЦБ: выпуск возможен '
                    'только в его информационной системе.'))
            if not record.issuer_id.coop_verified:
                raise UserError(_(
                    'Личность эмитента не подтверждена. Оператор проверит '
                    'это в любом случае — лучше пройти проверку до подачи.'))
            record.write({
                'state': 'submitted',
                'submitted_on': fields.Date.context_today(record),
            })
        return True

    def action_mark_issued(self):
        for record in self:
            record.write({
                'state': 'issued',
                'issued_on': fields.Date.context_today(record),
            })
        return True

    def action_reject(self):
        self.write({'state': 'rejected'})
        return True


class CoopCfaHolding(models.Model):
    """ЦФА участника, купленные у операторов.

    Платформа их не выпускает и не хранит — она показывает. Смысл в
    сводном виде: паи, токены на TON и ЦФА в одном месте, иначе участник
    держит свою имущественную картину в голове и в трёх приложениях.

    Заводится вручную или подтягивается интеграцией с оператором, когда
    она появится. Сейчас честнее сказать «данные внесены участником», чем
    делать вид, что мы сверились с реестром.
    """
    _name = 'coop.cfa.holding'
    _description = 'ЦФА на руках'
    _order = 'partner_id, id'

    partner_id = fields.Many2one(
        'res.partner', string='Держатель', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner())
    operator_id = fields.Many2one(
        'coop.cfa.operator', string='Оператор', required=True, index=True)
    issue_id = fields.Many2one(
        'coop.cfa.issue', string='Наш выпуск',
        help='Заполняется, если это выпуск участника платформы. Пусто — '
             'куплено на стороне.')

    name = fields.Char(string='Что за актив', required=True)
    quantity = fields.Float(string='Количество', digits=(16, 3), required=True)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    value = fields.Monetary(string='Оценка', currency_field='currency_id')
    maturity_date = fields.Date(string='Срок погашения')

    source = fields.Selection([
        ('manual', 'Внесено участником'),
        ('operator', 'Получено от оператора'),
    ], string='Откуда данные', default='manual', required=True,
        help='«Внесено участником» значит, что платформа этих сведений ни '
             'у кого не сверяла.')

    is_mine = fields.Boolean(
        string='Моё', compute='_compute_is_mine', search='_search_is_mine',
        help='Своё — то, что принадлежит участнику или организации, счета '
             'которой он ведёт.')

    def _my_partners(self):
        """Партнёры, от чьего лица действует пользователь."""
        return self.env.user.coop_treasury_partner_ids

    @api.depends_context('uid')
    def _compute_is_mine(self):
        mine = self._my_partners()
        for record in self:
            record.is_mine = record.partner_id in mine

    def _search_is_mine(self, operator, value):
        # Отбор идёт на сервере, а не выражением в самом действии:
        # клиентский разборщик выражений не понимает обращений к полям
        # пользователя, и вкладка «моё» не открывалась вовсе.
        # Odoo приводит «= True» к «in {True}» ещё до вызова поиска и
        # передаёт при этом свой набор, а не список. Поэтому значение
        # разбирается как последовательность, а не сверяется с типом:
        # иначе вкладка «моё» падала с ошибкой прямо при открытии.
        if isinstance(value, bool):
            wanted = value
        else:
            items = list(value)
            if len(items) != 1 or not isinstance(items[0], bool):
                raise ValueError('Поддерживается только «моё: да» или «моё: нет».')
            wanted = items[0]
        if operator in ('=', 'in'):
            positive = wanted
        elif operator in ('!=', 'not in'):
            positive = not wanted
        else:
            raise ValueError('Поддерживается только «моё: да» или «моё: нет».')
        return [('partner_id', 'in' if positive else 'not in',
                 self._my_partners().ids)]
