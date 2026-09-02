# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
    _inherit = ['mail.thread', 'mail.activity.mixin']
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

    city = fields.Char(string='Город', index=True)

    # ── Предмет ──────────────────────────────────────────────────────────
    resource_id = fields.Many2one('coop.resource', string='Объявление о ресурсе')
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
    state = fields.Selection([
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

    _sql_constraints = [
        ('number_uniq', 'unique(number)', 'Такой номер сделки уже есть.'),
        ('parties_differ', 'check(party_a_id != party_b_id)',
         'Сделка с самим собой не имеет смысла.'),
    ]

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

    @api.depends('review_ids.deal_id', 'review_ids.author_id')
    def _compute_reviews_visible(self):
        for record in self:
            authors = set(record.review_ids.mapped('author_id').ids)
            record.reviews_visible = bool(
                {record.party_a_id.id, record.party_b_id.id} <= authors)

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
                values['number'] = self.env['ir.sequence'].next_by_code(
                    'coop.deal') or _('Черновик')
        return super().create(vals_list)

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

    def _require_party(self):
        side = self._my_side()
        if not side:
            raise UserError(_(
                'Это чужая сделка. Действовать в ней могут только её стороны.'))
        return side

    # ── Действия ─────────────────────────────────────────────────────────

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
        return True

    def action_start(self):
        for record in self:
            record._require_party()
            record.state = 'active'
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
        return True

    def action_open_dispute(self):
        for record in self:
            side = record._require_party()
            record.write({
                'state': 'disputed',
                'dispute_opened_by_id': (record.party_a_id if side == 'a'
                                         else record.party_b_id).id,
            })
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
        return True

    def action_cancel(self):
        for record in self:
            record._require_party()
            record.state = 'cancelled'
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
    rating = fields.Selection([
        ('1', 'Плохо'), ('2', 'Так себе'), ('3', 'Нормально'),
        ('4', 'Хорошо'), ('5', 'Отлично'),
    ], string='Оценка', required=True, default='5')
    body = fields.Text(string='Отзыв')
    visible = fields.Boolean(
        related='deal_id.reviews_visible', store=True, string='Раскрыт')

    _sql_constraints = [
        ('one_per_author', 'unique(deal_id, author_id)',
         'Отзыв по этой сделке вы уже оставили.'),
        ('not_self', 'check(author_id != target_id)',
         'Оценивать самого себя не имеет смысла.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.deal_id.state != 'done':
                raise UserError(_(
                    'Отзыв оставляют по завершённой сделке. Пока она не '
                    'исполнена, оценивать нечего.'))
        return records

    def write(self, vals):
        if set(vals) - {'visible'}:
            raise UserError(_(
                'Отзыв не переписывают: он часть истории сделки. Если '
                'обстоятельства изменились, скажите об этом ответом.'))
        return super().write(vals)
