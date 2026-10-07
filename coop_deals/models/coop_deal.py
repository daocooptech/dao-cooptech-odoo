# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Кто платит — по ролям сторон, а не только по способу сделки (решение 427,
# владелец 28.09.2026: «исправь график платежей»). Способ сделки не знает,
# кем записана первая сторона: в «Юридическом сопровождении» первая сторона
# — исполнитель, и график заставлял платить исполнителя. На копии боевой
# так было в 72 сделках из 213.
PAYS_FIRST = ('purchase', 'rent', 'job', 'service', 'share', 'credit')
# График кредитной сделки — возврат долга: платит заёмщик, получает
# кредитор (так же было и по способу: у кредита первая сторона — заёмщик).
PAYER_ROLES = ('заказчик', 'покупатель', 'арендатор', 'заёмщик', 'заемщик',
               'наниматель', 'работодатель', 'приобретатель', 'пайщик', 'инвестор',
               'размещающий', 'участник')
PAYEE_ROLES = ('исполнитель', 'продавец', 'арендодатель', 'кредитор', 'займодавец',
               'подрядчик', 'поставщик', 'работник', 'кооператив', 'проект',
               'владелец склада', 'инициатор')


def _money_role(text):
    text = (text or '').strip().lower()
    if any(text.startswith(r) for r in PAYER_ROLES):
        return 'pays'
    if any(text.startswith(r) for r in PAYEE_ROLES):
        return 'gets'
    return None


class CoopDeal(models.Model):
    """Сделка между двумя участниками платформы.

    Почему не заказ Odoo. В заказе роли жёсткие: есть продавец и есть
    покупатель, и всё считается от продавца. На платформе стороны
    равноправны, а сделка бывает обменом, даром, вкладом в проект и
    взаимным кредитом — там продавца нет вовсе. Изображать это заказом с
    нулевой суммой значит врать в данных: отчёты, права и отзывы будут
    считаться от роли, которой в сделке не было.

    Поэтому здесь две стороны и у каждой своя роль в этой сделке.
    «Покупатель» и «продавец» — не свойства участников, а их положение в
    конкретной сделке: тот же человек в следующей окажется арендатором.

    Деньги через платформу не ходят. График платежей — учёт
    договорённости: стороны согласовали рассрочку, а факт оплаты
    отмечает получатель. Держать чужие деньги и переводить их по команде
    — банковская операция, и на неё нужна лицензия.
    """
    _name = 'coop.deal'
    _description = 'Сделка'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'coop.page.mixin']
    _order = 'signed_on desc, id desc'
    _rec_name = 'display_name'

    number = fields.Char(
        string='Номер', required=True, copy=False, index=True,
        default=lambda self: _('Черновик'),
        help='СД — сделка, год заключения, порядковый номер за этот год. '
             'Номер не меняется и не повторяется: по нему сделку находят '
             'и ссылаются на неё в переписке, актах и спорах.')
    name = fields.Char(string='Предмет сделки', required=True, tracking=True)
    display_name = fields.Char(compute='_compute_display_name', store=True)

    subject = fields.Selection([
        ('resource', 'Ресурс'),
        ('service', 'Услуга'),
        ('work', 'Работа'),
        ('project', 'Проект'),
        ('credit', 'Взаимный кредит'),
    ], string='Что передаётся', required=True, default='resource', index=True,
        tracking=True)

    # Значок предмета — чтобы карточка сделки читалась так же, как
    # остальные каталоги: у всех слева квадрат с картинкой или символом,
    # а не пустое место. Считается из предмета, руками не заполняется.
    ICONS = {'resource': '📦', 'service': '🛠', 'work': '🧰',
             'project': '🏗', 'credit': '🤝'}

    icon = fields.Char(string='Значок', compute='_compute_icon')

    @api.depends('subject')
    def _compute_icon(self):
        for record in self:
            record.icon = self.ICONS.get(record.subject, '📦')

    way = fields.Selection([
        ('sale', 'Продажа'),
        ('purchase', 'Покупка'),
        ('batch', 'Продажа партией'),
        ('rent', 'Аренда'),
        ('exchange', 'Обмен'),
        ('gift', 'Дар'),
        ('service', 'Услуга'),
        ('job', 'Работа по вакансии'),
        ('share', 'Доля в проекте'),
        ('credit', 'Взаимный кредит'),
    ], string='Каким образом', required=True, default='sale', index=True,
        tracking=True)

    # ── Стороны ──────────────────────────────────────────────────────────
    #
    # Ровно две и равноправные. Кто «первый», значения не имеет — это
    # порядок записи, а не старшинство.
    party_a_id = fields.Many2one(
        'res.partner', string='Сторона', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(), tracking=True)
    party_b_id = fields.Many2one(
        'res.partner', string='Вторая сторона', required=True, index=True,
        tracking=True)
    role_a = fields.Char(string='Роль стороны', help='Продавец, арендатор, исполнитель.')
    role_b = fields.Char(string='Роль второй стороны')
    author_id = fields.Many2one(
        'res.partner', string='Оформил', readonly=True, index=True,
        default=lambda self: self.env.user.partner_id)

    # Ответственный — на каждую сторону (решение 450, «максимальная
    # схожесть с битрикс24»). У человека это он сам. У организации — тот,
    # кому она поручила «Сделки»: он ведёт сделку, ему приходят дела и
    # извещения. Две стороны — два ответственных: у каждой свои люди, и
    # чужого ответственного сторона назначить не может.
    responsible_a_id = fields.Many2one(
        'res.users', string='Ответственный стороны', index=True,
        tracking=True, copy=False)
    responsible_b_id = fields.Many2one(
        'res.users', string='Ответственный второй стороны', index=True,
        tracking=True, copy=False)
    responsible_a_allowed_ids = fields.Many2many(
        'res.users', compute='_compute_responsible_allowed')
    responsible_b_allowed_ids = fields.Many2many(
        'res.users', compute='_compute_responsible_allowed')

    city = fields.Char(string='Город', index=True)

    # ── Предмет ──────────────────────────────────────────────────────────
    resource_id = fields.Many2one('coop.resource', string='Объявление о ресурсе')
    # Фотография предмета сделки. Через resource_id её брать не вышло:
    # связь пуста у всех четырёхсот десяти сделок — они заводились сами
    # по себе, а не из объявлений. Поэтому снимок хранится у сделки,
    # а подбирается по предмету при наполнении.
    image_512 = fields.Image(
        string='Фото предмета', max_width=512, max_height=512)
    skill_offer_id = fields.Many2one('coop.skill.offer', string='Предложение навыка')
    vacancy_id = fields.Many2one('coop.vacancy', string='Вакансия')
    project_id = fields.Many2one('coop.project', string='Проект')

    # ── Деньги ───────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)
    amount = fields.Monetary(
        string='Сумма', currency_field='currency_id', tracking=True,
        help='Ноль — это не пропуск: у дара и обмена суммы нет.')
    line_ids = fields.One2many('coop.deal.line', 'deal_id', string='Спецификация')
    payment_ids = fields.One2many('coop.deal.payment', 'deal_id', string='График платежей')
    amount_paid = fields.Monetary(
        string='Оплачено', currency_field='currency_id',
        compute='_compute_amount_paid', store=True)
    amount_due = fields.Monetary(
        string='Осталось', currency_field='currency_id',
        compute='_compute_amount_paid', store=True)

    # ── Состояние ────────────────────────────────────────────────────────
    #
    # «Обращение» — лид человека (решение 451, владелец 08.10.2026). CRM у
    # человека нет (решение 450), а потенциальные покупатели и продавцы
    # есть: отклик на объявление, звонок, просьба прислать цену. Это та же
    # сделка на первой стадии, а не отдельная сущность — как в Битрикс24
    # без лидов: ничего не конвертируется, обращение просто переходит в
    # переговоры или отменяется.
    #
    # Умолчание остаётся «Переговоры»: сделки, которые заводят другие
    # разделы (бартер, склад, лид CRM организации), обращение уже прошли.
    state = fields.Selection([
        ('lead', 'Обращение'),
        ('draft', 'Переговоры'),
        ('agreed', 'Согласована'),
        ('active', 'Исполняется'),
        ('acceptance', 'На приёмке'),
        ('done', 'Завершена'),
        ('disputed', 'Спор'),
        ('cancelled', 'Отменена'),
    ], string='Состояние', default='draft', required=True, index=True,
        tracking=True)

    signed_on = fields.Date(string='Заключена', tracking=True)
    closed_on = fields.Date(string='Закрыта', tracking=True)
    # Дата сделки в воронке аналитики: заключённая — по дате заключения,
    # обращение и переговоры — по дню появления (у них даты заключения
    # ещё нет, и отбор по ней выкидывал их из воронки).
    funnel_date = fields.Date(
        string='Дата в воронке', compute='_compute_funnel_date', store=True,
        index=True)

    @api.depends('signed_on', 'create_date')
    def _compute_funnel_date(self):
        for record in self:
            record.funnel_date = record.signed_on or (
                record.create_date and record.create_date.date())

    # ── Акт приёма-передачи ──────────────────────────────────────────────
    #
    # Сделка считается исполненной, когда акт подтвердили обе стороны.
    # Одностороннее «я всё сдал» ничего не значит: приёмка на то и
    # приёмка, что её делает принимающий.
    act_confirmed_a = fields.Boolean(string='Акт подтверждён стороной', readonly=True)
    act_confirmed_b = fields.Boolean(string='Акт подтверждён второй стороной', readonly=True)
    act_confirmed_on = fields.Date(string='Акт подписан', readonly=True)

    # ── Отзывы ───────────────────────────────────────────────────────────
    review_ids = fields.One2many('coop.deal.review', 'deal_id', string='Отзывы')
    can_review = fields.Boolean(
        string='Можно оставить отзыв', compute='_compute_can_review',
        help='Сделка завершена, я её сторона и ещё не оценивал.')
    reviews_visible = fields.Boolean(
        string='Отзывы раскрыты', compute='_compute_reviews_visible', store=True,
        help='Оба отзыва показываются одновременно — когда написаны оба. '
             'Иначе второй пишется с оглядкой на первый, а то и в отместку.')
    outcome = fields.Selection([
        ('none', 'Ещё не завершена'),
        ('pending', 'Ждём отзывов'),
        ('positive', 'Обе стороны довольны'),
        ('mixed', 'Оценки разошлись'),
        ('negative', 'Обе стороны недовольны'),
    ], string='Итог', compute='_compute_outcome', store=True)

    # ── Спор ─────────────────────────────────────────────────────────────
    dispute_opened_by_id = fields.Many2one(
        'res.partner', string='Спор открыл', readonly=True)
    dispute_reason = fields.Text(string='Существо спора')
    dispute_resolution = fields.Text(string='Решение по спору')
    dispute_resolved_by_id = fields.Many2one(
        'res.users', string='Спор разобрал', readonly=True)
    dispute_resolved_on = fields.Date(string='Спор закрыт', readonly=True)

    import_key = fields.Char(string='Ключ источника', index=True, copy=False)

    _number_uniq = models.Constraint(
        'unique(number)',
        'Такой номер сделки уже есть.',
    )
    _parties_differ = models.Constraint(
        'check(party_a_id != party_b_id)',
        'Сделка с самим собой не имеет смысла.',
    )

    @api.depends('number', 'name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = '%s — %s' % (record.number, record.name or '')

    @api.depends('payment_ids.amount', 'payment_ids.state', 'amount')
    def _compute_amount_paid(self):
        for record in self:
            paid = sum(record.payment_ids.filtered(
                lambda p: p.state == 'paid').mapped('amount'))
            record.amount_paid = paid
            record.amount_due = max(0, (record.amount or 0) - paid)

    @api.depends('review_ids.deal_id', 'review_ids.side')
    def _compute_reviews_visible(self):
        """Раскрываем, когда высказались обе стороны.

        По сторонам, а не по авторам. От лица организации действует
        человек, которому она поручила дела, и автором отзыва стоит он —
        не сама организация. Пока условие требовало совпадения авторов со
        сторонами, отзывы по сделке с организацией не раскрывались
        никогда: оба написаны, оба скрыты, итог сделки навсегда
        «ожидается». Проверено 15 сентября 2026 на сделке СД-2026-000271.
        """
        for record in self:
            sides = set(record.review_ids.mapped('side'))
            record.reviews_visible = {'a', 'b'} <= sides

    @api.depends('state', 'reviews_visible', 'review_ids.rating')
    def _compute_outcome(self):
        for record in self:
            if record.state != 'done':
                record.outcome = 'none'
            elif not record.reviews_visible:
                record.outcome = 'pending'
            else:
                # Оценка хранится строкой — это перечисление, а не число.
                good = [int(r.rating) >= 4 for r in record.review_ids if r.rating]
                if all(good):
                    record.outcome = 'positive'
                elif not any(good):
                    record.outcome = 'negative'
                else:
                    record.outcome = 'mixed'

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if not values.get('number') or values['number'] == _('Черновик'):
                # Нумератор — общий на площадку, без отбора по текущей
                # компании: next_by_code ищет только в ней, и у того, кто
                # действует из компании учёта своей организации (решение
                # 449), нумератор не находился — сделка получала
                # «Черновик», а вторая такая же падала на уникальности.
                sequence = self.env['ir.sequence'].sudo().search(
                    [('code', '=', 'coop.deal')], order='company_id', limit=1)
                values['number'] = (sequence._next() if sequence else False) \
                    or _('Черновик')
        records = super().create(vals_list)
        records._coop_fill_responsibles()
        return records

    def write(self, vals):
        # Ответственного стороны назначает сама сторона: человек — себя,
        # организация — тот, у кого её «Сделки». Вторая сторона и автор
        # сделки здесь не решают.
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            for side in ('a', 'b'):
                if 'responsible_%s_id' % side not in vals:
                    continue
                for record in self:
                    party = record['party_%s_id' % side]
                    if not self.env.user.coop_has_power('deal', party):
                        raise UserError(_(
                            'Ответственного стороны «%s» назначает она сама: '
                            'человек или тот, кому организация поручила '
                            'сделки.') % party.display_name)
        # Сменилась сторона — прежний ответственный ей чужой: снимаем и
        # подбираем заново из её людей.
        for side in 'ab':
            if 'party_%s_id' % side in vals and 'responsible_%s_id' % side not in vals:
                vals = dict(vals, **{'responsible_%s_id' % side: False})
        before = {(r.id, s): r['responsible_%s_id' % s] for r in self for s in 'ab'}
        result = super().write(vals)
        if {'party_a_id', 'party_b_id'} & set(vals):
            self._coop_fill_responsibles()
        for record in self:
            for side in 'ab':
                user = record['responsible_%s_id' % side]
                if user and user != before[(record.id, side)] \
                        and user != self.env.user:
                    self.env['coop.notification'].sudo()._notify(
                        user.partner_id, _(
                            'Вы назначены ответственным по сделке %s.')
                        % record.display_name, record=record, kind='deal')
        return result

    # ── Ответственные ────────────────────────────────────────────────────

    @api.model
    def _coop_side_staff(self, partner):
        """Кто может отвечать за сделку от имени стороны."""
        if not partner:
            return self.env['res.users']
        if not partner.is_company:
            return partner.sudo().user_ids.filtered('active')
        return self.env['coop.membership'].sudo().search([
            ('organization_id', '=', partner.id), ('state', '=', 'active'),
            ('power_ids.code', '=', 'deal'),
        ], order='joined_on, id').partner_id.user_ids.filtered('active')

    @api.depends('party_a_id', 'party_b_id')
    def _compute_responsible_allowed(self):
        for record in self:
            record.responsible_a_allowed_ids = self._coop_side_staff(record.party_a_id)
            record.responsible_b_allowed_ids = self._coop_side_staff(record.party_b_id)

    def _coop_fill_responsibles(self):
        """Проставить ответственных там, где их нет.

        Тот, кто завёл сделку, отвечает за свою сторону, если может; иначе
        — первый по стажу держатель «Сделок». Нет такого — поле пустое, и
        сделка видна в фильтре «Нет ответственного».
        """
        me = self.env.user
        for record in self:
            values = {}
            for side in 'ab':
                if record['responsible_%s_id' % side]:
                    continue
                staff = self._coop_side_staff(record['party_%s_id' % side])
                if staff:
                    values['responsible_%s_id' % side] = (
                        me if me in staff else staff[0]).id
            if values:
                # Без строки в ленте: подбор — не событие сделки, а её
                # исходное состояние, и «None → Иванов» от OdooBot в каждой
                # из сотен сделок только засоряет ленту.
                super(CoopDeal, record.sudo().with_context(
                    mail_notrack=True)).write(values)
        return True

    @api.constrains('responsible_a_id', 'responsible_b_id', 'party_a_id', 'party_b_id')
    def _check_responsibles(self):
        for record in self:
            for side in 'ab':
                user = record['responsible_%s_id' % side]
                if user and user not in self._coop_side_staff(
                        record['party_%s_id' % side]):
                    raise ValidationError(_(
                        '%(user)s не может отвечать за сторону «%(party)s»: '
                        'отвечает сам человек или тот, кому организация '
                        'поручила сделки.',
                        user=user.name,
                        party=record['party_%s_id' % side].display_name))

    def _coop_my_responsible(self):
        """Ответственный моей стороны — ему по умолчанию и пишется дело."""
        self.ensure_one()
        side = self._my_side()
        return self['responsible_%s_id' % side] if side else self.env['res.users']

    def action_coop_plan_activity(self):
        """«Запланировать дело» в блоке «Что дальше»."""
        self.ensure_one()
        user = self._coop_my_responsible() or self.env.user
        return {
            'type': 'ir.actions.act_window',
            'name': _('Что дальше по сделке %s') % self.number,
            'res_model': 'mail.activity.schedule',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'active_model': self._name,
                'active_ids': self.ids,
                'active_id': self.id,
                'default_activity_user_id': user.id,
            },
        }

    @api.model
    def _coop_release_responsible(self, user, organization):
        """Человек больше не ведёт сделки организации.

        Сделки, где он отвечал за неё, остаются без ответственного, а
        руководителю (полномочие «Подпись», иначе «Представительство»)
        ставится дело — назначить нового.
        """
        Deal = self.sudo()
        open_states = ('lead', 'draft', 'agreed', 'active', 'acceptance', 'disputed')
        heads = self.env['coop.membership'].sudo().search([
            ('organization_id', '=', organization.id), ('state', '=', 'active'),
            ('partner_id.user_ids', '!=', False)])
        head = (heads.filtered(lambda m: 'sign' in m.power_ids.mapped('code'))
                or heads.filtered(lambda m: 'represent' in m.power_ids.mapped('code'))
                )[:1].partner_id.user_ids.filtered('active')[:1]
        released = Deal
        for side in 'ab':
            deals = Deal.search([
                ('party_%s_id' % side, '=', organization.id),
                ('responsible_%s_id' % side, '=', user.id),
                ('state', 'in', open_states)])
            if deals:
                super(CoopDeal, deals).write({'responsible_%s_id' % side: False})
                released |= deals
        if head:
            for deal in released:
                deal.activity_schedule(
                    'mail.mail_activity_data_todo', user_id=head.id,
                    summary=_('Назначить ответственного'),
                    note=_('%s больше не ведёт сделки организации.') % user.name)
        return released

    # ── Кто есть кто ─────────────────────────────────────────────────────

    def _my_side(self):
        """С какой стороны сделки стоит тот, кто её открыл.

        Возвращает 'a', 'b' или False. Нужно затем, что действия сторон
        различаются: подтвердить акт может каждая за себя, и путать эти
        две галочки нельзя.
        """
        self.ensure_one()
        mine = self.env.user.coop_actor_partner_ids
        if self.party_a_id in mine:
            return 'a'
        if self.party_b_id in mine:
            return 'b'
        return False

    def _coop_payer_payee(self):
        """Кто платит и кто получает: по ролям сторон, затем по способу."""
        self.ensure_one()
        a, b = self.party_a_id, self.party_b_id
        role_a, role_b = _money_role(self.role_a), _money_role(self.role_b)
        if role_a == 'pays' or role_b == 'gets':
            return a, b
        if role_a == 'gets' or role_b == 'pays':
            return b, a
        if self.way in PAYS_FIRST:
            return a, b
        return b, a

    def _require_party(self):
        side = self._my_side()
        if not side:
            raise UserError(_(
                'Это чужая сделка. Действовать в ней могут только её стороны.'))
        return side

    # ── Стороны ──────────────────────────────────────────────────────────

    def _other_partner(self):
        """Вторая сторона сделки — та, что не я."""
        self.ensure_one()
        mine = self.env.user.coop_actor_partner_ids
        other_item = (self.party_a_id | self.party_b_id) - mine
        return other_item[:1]

    @api.depends_context('uid')
    @api.depends('state', 'review_ids.author_id')
    def _compute_can_review(self):
        """Отзыв оставляют по завершённой сделке и только один раз.

        Признак считается теми же условиями, что и проверка при записи
        отзыва, — иначе кнопка отвечала бы отказом.
        """
        mine = self.env.user.coop_actor_partner_ids
        for record in self:
            already = bool(record.review_ids.filtered(
                lambda r: r.author_id in mine))
            record.can_review = bool(
                record.state == 'done'
                and not already
                and (record.party_a_id | record.party_b_id) & mine)

    def action_review(self):
        """Открыть окно отзыва."""
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_(
                'Отзыв оставляют по завершённой сделке. Пока она не '
                'исполнена, оценивать нечего.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Отзыв по сделке %s') % self.display_name,
            'res_model': 'coop.deal.review.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_deal_id': self.id},
        }

    # ── Извещения ────────────────────────────────────────────────────────

    def _notify_other(self, body):
        """Известить вторую сторону о том, что сделка сдвинулась.

        Каждый переход меняет сделку для обоих, а знает о нём только тот,
        кто нажал кнопку. До извещений вторая сторона узнавала о
        согласовании, начале исполнения и даже о споре, только открыв
        сделку по своей воле, — то есть случайно.

        Вторая сторона считается вычитанием: так работает и у стороны
        «а», и у стороны «б», и у администратора, разбирающего спор, —
        ему вычитать нечего, и извещение уходит обоим.
        """
        self.ensure_one()
        mine = self.env.user.coop_actor_partner_ids
        other_item = (self.party_a_id | self.party_b_id) - mine
        if other_item:
            self.env['coop.notification']._notify(
                other_item, body, record=self, kind='deal')

    # ── Действия ─────────────────────────────────────────────────────────

    def action_negotiate(self):
        """Принять обращение: дальше по сделке идут переговоры."""
        for record in self:
            record._require_party()
            if record.state != 'lead':
                raise UserError(_(
                    'Переговоры начинают из обращения. Сделка %s уже дальше.')
                    % record.display_name)
            record.state = 'draft'
            record._notify_other(_(
                'По обращению %s начаты переговоры.') % record.display_name)
        return True

    def action_agree(self):
        """Согласовать сделку.

        Обе стороны должны быть с подтверждённой личностью: сделка — это
        обязательство, и знать, с кем имеешь дело, вправе каждая сторона.
        """
        for record in self:
            record._require_party()
            for party in (record.party_a_id, record.party_b_id):
                party.coop_require_level('identity', _('заключить сделку'))
            record.write({
                'state': 'agreed',
                'signed_on': record.signed_on or fields.Date.context_today(record),
            })
            record._notify_other(_(
                'Сделка %(number)s согласована: «%(subject)s».',
                number=record.display_name, subject=record.name))
        return True

    def action_start(self):
        for record in self:
            record._require_party()
            record.state = 'active'
            record._notify_other(_(
                'По сделке %s началось исполнение.') % record.display_name)
        return True

    def action_confirm_act(self):
        """Подтвердить акт со своей стороны.

        Когда подтвердят обе — сделка исполнена и открываются отзывы.
        """
        for record in self:
            side = record._require_party()
            record.write({'act_confirmed_%s' % side: True,
                          'state': 'acceptance'})
            if record.act_confirmed_a and record.act_confirmed_b:
                record.write({
                    'state': 'done',
                    'act_confirmed_on': fields.Date.context_today(record),
                    'closed_on': fields.Date.context_today(record),
                })
                record.message_post(body=_(
                    'Акт подтверждён обеими сторонами. Сделка исполнена, '
                    'отзывы открыты.'))
                # Счётчик завершённых сделок у обеих сторон: он показан
                # на странице человека и участвует в уровне доверия.
                (record.party_a_id | record.party_b_id).sudo()                    ._coop_recompute_deal_stats()
                record._notify_other(_(
                    'Сделка %s исполнена: акт подтверждён обеими сторонами. '
                    'Можно оставить отзыв.') % record.display_name)
            else:
                # Пока подтвердила одна сторона, вторая об этом не знает —
                # и сделка стоит на месте ровно из-за этого.
                record._notify_other(_(
                    'По сделке %s подтверждён акт с одной стороны — ждём '
                    'вашего подтверждения.') % record.display_name)
        return True

    def action_open_dispute(self):
        for record in self:
            side = record._require_party()
            record.write({
                'state': 'disputed',
                'dispute_opened_by_id': (record.party_a_id if side == 'a'
                                         else record.party_b_id).id,
            })
            record._notify_other(_(
                'По сделке %s открыт спор — требуется ваше решение.')
                % record.display_name)
        return True

    def action_resolve_dispute(self):
        """Закрыть спор.

        Разбирает администратор платформы — решение владельца для MVP.
        Решение записывается и остаётся в истории: спор, закрытый без
        объяснения, ничем не отличается от замолчанного.
        """
        for record in self:
            if not self.env.user.has_group('base.group_system'):
                raise UserError(_(
                    'Спор разбирает администратор платформы.'))
            if not record.dispute_resolution:
                raise UserError(_(
                    'Запишите решение по спору. Спор, закрытый без '
                    'объяснения, ничем не отличается от замолчанного.'))
            record.write({
                'state': 'done',
                'dispute_resolved_by_id': self.env.user.id,
                'dispute_resolved_on': fields.Date.context_today(record),
                'closed_on': fields.Date.context_today(record),
            })
            # Обеим сторонам: администратор в сделке не сторона, и
            # вычитать из пары некого — извещение уходит и той, и другой.
            (record.party_a_id | record.party_b_id).sudo()                ._coop_recompute_deal_stats()
            record._notify_other(_(
                'Спор по сделке %s закрыт администратором платформы.')
                % record.display_name)
        return True

    def action_cancel(self):
        for record in self:
            record._require_party()
            record.state = 'cancelled'
            record._notify_other(_(
                'Сделка %s отменена второй стороной.') % record.display_name)
        return True


class CoopDealLine(models.Model):
    """Строка спецификации: что именно, сколько и по какой цене."""
    _name = 'coop.deal.line'
    _description = 'Строка сделки'
    _order = 'sequence, id'

    deal_id = fields.Many2one(
        'coop.deal', string='Сделка', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='Порядок', default=10)
    name = fields.Char(string='Что передаётся', required=True)
    quantity = fields.Float(string='Количество', default=1.0)
    uom_name = fields.Char(string='Единица', default='шт.')
    price_unit = fields.Monetary(string='Цена за единицу', currency_field='currency_id')
    subtotal = fields.Monetary(
        string='Сумма', currency_field='currency_id',
        compute='_compute_subtotal', store=True)
    currency_id = fields.Many2one(related='deal_id.currency_id', store=True)

    @api.depends('quantity', 'price_unit')
    def _compute_subtotal(self):
        for record in self:
            record.subtotal = record.quantity * record.price_unit


class CoopDealPayment(models.Model):
    """Платёж по графику — учёт договорённости, а не движение денег.

    Деньги через платформу не ходят: держать чужие средства и переводить
    их по команде — банковская операция. Здесь записано, что стороны
    условились заплатить и что получатель подтвердил получение.
    """
    _name = 'coop.deal.payment'
    _description = 'Платёж по сделке'
    _inherit = ['mail.thread']
    _order = 'due_on, id'

    deal_id = fields.Many2one(
        'coop.deal', string='Сделка', required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Назначение', default='Платёж по договору')
    due_on = fields.Date(string='Срок', required=True)

    # Кто кому платит — явными полями. Выводить это из порядка сторон в
    # сделке нельзя: стороны равноправны, «первая» — порядок полей, а не
    # старшинство. На покупке знак перевернулся бы, и взаиморасчёты
    # уверенно показывали бы «должны вам» там, где должны вы.
    payer_id = fields.Many2one(
        'res.partner', string='Платит', index=True,
        compute='_compute_parties', store=True, readonly=False,
        help='Кто по этому платежу передаёт деньги.')
    payee_id = fields.Many2one(
        'res.partner', string='Получает', index=True,
        compute='_compute_parties', store=True, readonly=False,
        help='Кто по этому платежу деньги получает — он же и подтверждает '
             'получение.')
    amount = fields.Monetary(string='Сумма', currency_field='currency_id', required=True)
    currency_id = fields.Many2one(related='deal_id.currency_id', store=True)
    state = fields.Selection([
        ('planned', 'Ожидается'),
        ('paid', 'Оплачен'),
        ('overdue', 'Просрочен'),
        ('cancelled', 'Отменён'),
    ], string='Состояние', default='planned', required=True, index=True, tracking=True)
    paid_on = fields.Date(string='Отмечен оплаченным', readonly=True)
    confirmed_by_id = fields.Many2one(
        'res.users', string='Подтвердил получение', readonly=True)

    @api.depends('deal_id.way', 'deal_id.party_a_id', 'deal_id.party_b_id',
                 'deal_id.role_a', 'deal_id.role_b')
    def _compute_parties(self):
        """Предположить стороны платежа по способу сделки.

        Предположить, а не задать: поле остаётся правимым. Способ сделки
        подсказывает, кто передаёт деньги — при покупке первая сторона
        платит, при продаже получает, — но случаи бывают разные, и
        последнее слово за теми, кто сделку заключает.
        """
        for record in self:
            deal = record.deal_id
            if not deal:
                record.payer_id = record.payee_id = False
                continue
            if record.payer_id and record.payee_id:
                continue
            record.payer_id, record.payee_id = deal._coop_payer_payee()

    @api.model
    def _coop_fix_directions(self):
        """Развернуть строки графика, где плательщик противоречит ролям.

        Вызывается из данных при каждом обновлении модуля. Трогает только
        строки, где стороны — ровно стороны сделки и роли говорят обратное;
        строку, у которой роли ничего не говорят, оставляет как есть.
        """
        fixed = 0
        for line in self.sudo().search([('payer_id', '!=', False), ('payee_id', '!=', False)]):
            deal = line.deal_id
            if not deal or {line.payer_id, line.payee_id} != {deal.party_a_id, deal.party_b_id}:
                continue
            if not (_money_role(deal.role_a) or _money_role(deal.role_b)):
                continue
            payer, payee = deal._coop_payer_payee()
            if line.payer_id != payer:
                line.write({'payer_id': payer.id, 'payee_id': payee.id})
                fixed += 1
        if fixed:
            _logger.info('График платежей: развёрнуто строк %s', fixed)
        return True

    def action_mark_paid(self):
        """Отметить получение.

        Отмечает получатель, а не плательщик: «я заплатил» — это
        утверждение одной стороны, «я получил» — подтверждение другой, и
        доказательная сила у них разная.
        """
        for record in self:
            record.deal_id._require_party()
            record.write({
                'state': 'paid',
                'paid_on': fields.Date.context_today(record),
                'confirmed_by_id': self.env.user.id,
            })
            # Плательщику: он отдал деньги и до сих пор не знал, дошли ли
            # они. Отмечает получение вторая сторона, и только она может
            # об этом сообщить.
            record.deal_id._notify_other(_(
                'Платёж по сделке %(number)s получен: %(amount)s.',
                number=record.deal_id.display_name, amount=record.amount))
        return True

    @api.model
    def _cron_mark_overdue(self):
        stale = self.search([
            ('state', '=', 'planned'),
            ('due_on', '<', fields.Date.context_today(self)),
        ])
        if stale:
            stale.write({'state': 'overdue'})
        return True


class CoopDealReview(models.Model):
    """Двусторонний отзыв по сделке.

    Оба отзыва показываются одновременно — когда написаны оба. Если
    открывать сразу, второй пишется с оглядкой на первый, а то и в
    отместку, и обе оценки перестают значить что-либо.

    Отзыв нельзя переписать: он часть истории сделки. Ошибку исправляют
    ответом, а не правкой сказанного.
    """
    _name = 'coop.deal.review'
    _description = 'Отзыв по сделке'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    deal_id = fields.Many2one(
        'coop.deal', string='Сделка', required=True, ondelete='cascade', index=True)
    author_id = fields.Many2one(
        'res.partner', string='Кто оценивает', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner())
    target_id = fields.Many2one(
        'res.partner', string='Кого оценивают', required=True, index=True)
    side = fields.Selection([
        ('a', 'Первая сторона'),
        ('b', 'Вторая сторона'),
    ], string='Чей отзыв', index=True,
        help='Сторона сделки, от имени которой оставлен отзыв. Автором '
             'может быть уполномоченный организации, а сторона — сама '
             'организация.')
    rating = fields.Selection([
        ('1', 'Плохо'), ('2', 'Так себе'), ('3', 'Нормально'),
        ('4', 'Хорошо'), ('5', 'Отлично'),
    ], string='Оценка', required=True, default='5')
    body = fields.Text(string='Отзыв')
    visible = fields.Boolean(
        related='deal_id.reviews_visible', store=True, string='Раскрыт')

    _one_per_side = models.Constraint(
        'unique(deal_id, side)',
        'Отзыв по этой сделке от вашей стороны уже оставлен.',
    )

    def init(self):
        """Проставить сторону отзывам, заведённым до её появления.

        Без этого раскрытие по сторонам не сработало бы ни для одного
        старого отзыва: сторона пуста, множество из двух не собирается,
        и триста с лишним отзывов остались бы скрытыми навсегда.

        Раньше автором мог быть только сам участник сделки — по нему
        сторона и восстанавливается однозначно.
        """
        self.env.cr.execute("""
            UPDATE coop_deal_review r
               SET side = CASE WHEN r.author_id = d.party_a_id THEN 'a'
                               ELSE 'b' END
              FROM coop_deal d
             WHERE d.id = r.deal_id AND r.side IS NULL
        """)
        # Правка шла напрямую в базу, и сохранённые вычисляемые поля о
        # ней не знают: признак раскрытия и итог сделки остались бы
        # прежними. Пересчитываем их явно — иначе триста отзывов
        # проставлены, а на экране по-прежнему «ожидается».
        deals = self.env['coop.deal'].sudo().search([
            ('review_ids', '!=', False)])
        if deals:
            deals._compute_reviews_visible()
            deals._compute_outcome()
            deals.flush_recordset(['reviews_visible', 'outcome'])
    _not_self = models.Constraint(
        'check(author_id != target_id)',
        'Оценивать самого себя не имеет смысла.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('side') and vals.get('deal_id'):
                deal = self.env['coop.deal'].browse(vals['deal_id'])
                # Сторона — по автору, если он назван: от текущего
                # пользователя её можно взять, только когда пишет он сам.
                # Под суперпользователем (загрузчик, перенос) оба отзыва
                # получали сторону «a» и упирались в one_per_side.
                author = vals.get('author_id')
                if author and author == deal.party_a_id.id:
                    vals['side'] = 'a'
                elif author and author == deal.party_b_id.id:
                    vals['side'] = 'b'
                else:
                    vals['side'] = deal._my_side() or 'a'
        records = super().create(vals_list)
        for record in records:
            if record.deal_id.state != 'done':
                raise UserError(_(
                    'Отзыв оставляют по завершённой сделке. Пока она не '
                    'исполнена, оценивать нечего.'))
            # Пока второй отзыв не написан, оба скрыты — и тот, кого
            # оценили, об этом даже не знает. Извещаем не оценкой, а
            # самим фактом: оценку он увидит, когда ответит своей, и это
            # ровно то, ради чего отзывы раскрываются одновременно.
            record.target_id.sudo()._coop_recompute_deal_stats()
            if record.deal_id.reviews_visible:
                record.deal_id._notify_other(_(
                    'Отзывы по сделке %s раскрыты: обе стороны оценили '
                    'друг друга.') % record.deal_id.display_name)
            else:
                record.deal_id._notify_other(_(
                    'По сделке %s вас оценили. Отзыв раскроется, когда вы '
                    'оставите свой.') % record.deal_id.display_name)
        return records

    def write(self, vals):
        if set(vals) - {'visible'}:
            raise UserError(_(
                'Отзыв не переписывают: он часть истории сделки. Если '
                'обстоятельства изменились, скажите об этом ответом.'))
        return super().write(vals)
