# -*- coding: utf-8 -*-
"""Совместные закупки: оптовая цена в складчину.

Механика описана в макете тремя плитками, и они же задают устройство:
организатор находит поставщика и минимальный объём, цена падает по
уровням по мере набора, к дате «стопа» сбор закрывается, товар приходит
одной партией и раздаётся через точку самовывоза.

Два решения, которые стоит держать в голове при чтении кода.

**Цена пересчитывается для всех сразу, а не для тех, кто заказал
позже.** Иначе набравшийся объём премировал бы опоздавших: первые
заказали дорого, последние сбили цену и получили её только себе. В
складчине так нельзя — она перестаёт быть складчиной.

**Оргсбор входит в цену, а не добавляется сверху.** Участник видит одно
число и сравнивает его с магазином, а не считает в уме, сколько выйдет с
надбавкой. Размер сбора при этом виден в карточке: скрывать его — значит
делать вид, что организатор работает даром.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopGroupBuy(models.Model):
    _name = 'coop.groupbuy'
    _description = 'Совместная закупка'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'stop_date, id desc'

    name = fields.Char(string='Что закупаем', required=True, tracking=True)
    active = fields.Boolean(default=True)

    organizer_id = fields.Many2one(
        'res.partner', string='Организатор', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(),
        tracking=True,
        help='Находит поставщика, ведёт сбор заказов, принимает партию и '
             'раздаёт её участникам.')
    supplier_name = fields.Char(
        string='Поставщик', help='У кого закупаем. Может не быть участником '
                                 'платформы — это обычное дело.')
    city = fields.Char(string='Город', index=True)
    pickup_point = fields.Char(
        string='Точка самовывоза',
        help='Куда приезжать за своим после довоза.')

    unit_label = fields.Char(string='Единица', default='шт.', required=True)
    min_volume = fields.Float(
        string='Минимальный выкуп', digits=(16, 3), required=True,
        help='Меньше этого объёма поставщик партию не отгрузит.')
    base_price = fields.Float(
        string='Цена при минимальном объёме', digits=(16, 2), required=True,
        help='Оргсбор уже включён.')
    org_fee_percent = fields.Float(
        string='Оргсбор, %', default=7.0, digits=(5, 2),
        help='Доля организатора внутри цены. Показывается участнику: '
             'скрывать её — делать вид, что организатор работает даром.')

    stop_date = fields.Date(
        string='Стоп', required=True, index=True, tracking=True,
        help='До этого дня можно заказывать; после — сбор закрыт.')
    delivery_date = fields.Date(string='Ожидаемый довоз')

    description = fields.Html(string='Условия')

    tier_ids = fields.One2many(
        'coop.groupbuy.tier', 'groupbuy_id', string='Уровни цены')
    order_ids = fields.One2many(
        'coop.groupbuy.order', 'groupbuy_id', string='Заказы')

    state = fields.Selection([
        ('collecting', 'Идёт сбор'),
        ('stopped', 'Сбор закрыт'),
        ('delivering', 'Ждём довоз'),
        ('handout', 'Раздача'),
        ('done', 'Завершена'),
        ('cancelled', 'Не состоялась'),
    ], string='Состояние', default='collecting', required=True, index=True,
        tracking=True)

    total_quantity = fields.Float(
        string='Набрано', compute='_compute_totals', store=True, digits=(16, 3))
    total_amount = fields.Float(
        string='Сумма заказов', compute='_compute_totals', store=True,
        digits=(16, 2))
    participant_count = fields.Integer(
        string='Участников', compute='_compute_totals', store=True)
    current_price = fields.Float(
        string='Цена сейчас', compute='_compute_current_price', store=True,
        digits=(16, 2))
    progress = fields.Float(
        string='Набрано, %', compute='_compute_current_price', store=True,
        digits=(5, 1))

    my_quantity = fields.Float(
        string='Мой заказ', compute='_compute_my_order', digits=(16, 3))

    _min_volume_positive = models.Constraint(
        'check(min_volume > 0)',
        'Минимальный выкуп должен быть больше нуля.',
    )
    _base_price_positive = models.Constraint(
        'check(base_price > 0)',
        'Цена должна быть больше нуля.',
    )

    @api.depends('order_ids.quantity', 'order_ids.amount', 'order_ids.state')
    def _compute_totals(self):
        for record in self:
            live = record.order_ids.filtered(lambda o: o.state != 'cancelled')
            record.total_quantity = sum(live.mapped('quantity'))
            record.total_amount = sum(live.mapped('amount'))
            record.participant_count = len(live.mapped('partner_id'))

    @api.depends('total_quantity', 'base_price', 'min_volume',
                 'tier_ids.from_quantity', 'tier_ids.price')
    def _compute_current_price(self):
        """Цена по набранному объёму — одна на всех.

        Берётся самый выгодный уровень, порог которого уже пройден. Если
        уровней нет или ни один не пройден, действует цена минимального
        выкупа.
        """
        for record in self:
            price = record.base_price
            for tier in record.tier_ids.sorted('from_quantity'):
                if record.total_quantity >= tier.from_quantity:
                    price = tier.price
            record.current_price = price
            record.progress = (
                min(record.total_quantity / record.min_volume * 100, 999.9)
                if record.min_volume else 0.0)

    @api.depends_context('uid')
    @api.depends('order_ids.quantity', 'order_ids.partner_id', 'order_ids.state')
    def _compute_my_order(self):
        me = self.env.user._coop_acting_partner()
        for record in self:
            mine = record.order_ids.filtered(
                lambda o: o.partner_id == me and o.state != 'cancelled')
            record.my_quantity = sum(mine.mapped('quantity'))

    # ── Действия ─────────────────────────────────────────────────────────

    def action_stop(self):
        """Закрыть сбор заказов.

        Если минимальный выкуп не набран, закупка не состоялась: партию
        поставщик не отгрузит, и делать вид, что всё идёт своим чередом,
        нечестно по отношению к тем, кто уже заказал.
        """
        for record in self:
            if record.state != 'collecting':
                raise UserError(_('Сбор по этой закупке уже закрыт.'))
            if record.total_quantity < record.min_volume:
                record.write({'state': 'cancelled'})
                record.message_post(body=_(
                    'Закупка не состоялась: набрано %(got)s из %(need)s '
                    '%(unit)s. Заказы отменены.',
                    got=record.total_quantity, need=record.min_volume,
                    unit=record.unit_label))
                record.order_ids.write({'state': 'cancelled'})
                continue
            record.write({'state': 'stopped'})
            record.order_ids.filtered(lambda o: o.state == 'draft').write(
                {'state': 'confirmed'})
            record.message_post(body=_(
                'Сбор закрыт: %(got)s %(unit)s по цене %(price)s ₽.',
                got=record.total_quantity, unit=record.unit_label,
                price=record.current_price))
        return True

    def action_delivering(self):
        self.write({'state': 'delivering'})
        return True

    def action_handout(self):
        """Партия пришла — начинается раздача."""
        for record in self:
            record.write({'state': 'handout'})
            record.message_post(body=_(
                'Партия пришла. Забирать: %(where)s.',
                where=record.pickup_point or _('уточняется')))
        return True

    def action_done(self):
        """Закупка завершена — все забрали своё."""
        for record in self:
            waiting = record.order_ids.filtered(
                lambda o: o.state == 'confirmed')
            if waiting:
                raise UserError(_(
                    'Ещё %s участников не забрали заказ. Пока они не '
                    'забрали, закупка не завершена.') % len(waiting))
            record.write({'state': 'done'})
        return True


class CoopGroupBuyTier(models.Model):
    """Уровень цены: сколько набрали — столько стоит.

    Уровни задаёт организатор по договорённости с поставщиком. Порог —
    общий объём заказа, а не объём одного участника: в этом весь смысл
    складчины.
    """
    _name = 'coop.groupbuy.tier'
    _description = 'Уровень цены совместной закупки'
    _order = 'from_quantity'

    groupbuy_id = fields.Many2one(
        'coop.groupbuy', string='Закупка', required=True, ondelete='cascade',
        index=True)
    from_quantity = fields.Float(
        string='От объёма', required=True, digits=(16, 3))
    price = fields.Float(string='Цена за единицу', required=True, digits=(16, 2))

    _price_positive = models.Constraint(
        'check(price > 0)',
        'Цена уровня должна быть больше нуля.',
    )


class CoopGroupBuyOrder(models.Model):
    """Заказ участника в складчине."""
    _name = 'coop.groupbuy.order'
    _description = 'Заказ в совместной закупке'
    _order = 'create_date desc, id desc'

    groupbuy_id = fields.Many2one(
        'coop.groupbuy', string='Закупка', required=True, ondelete='cascade',
        index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Участник', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner())
    quantity = fields.Float(string='Сколько', required=True, digits=(16, 3))
    amount = fields.Float(
        string='К оплате', compute='_compute_amount', store=True,
        digits=(16, 2))

    state = fields.Selection([
        ('draft', 'В сборе'),
        ('confirmed', 'Подтверждён'),
        ('taken', 'Забран'),
        ('cancelled', 'Отменён'),
    ], string='Состояние', default='draft', required=True, index=True)

    _quantity_positive = models.Constraint(
        'check(quantity > 0)',
        'Заказать можно только положительное количество.',
    )

    @api.depends('quantity', 'groupbuy_id.current_price')
    def _compute_amount(self):
        """Сумма считается по текущей цене — она общая для всех.

        Поэтому заказавший первым платит столько же, сколько заказавший
        последним: набранный объём удешевляет партию целиком, а не
        отдельные заказы.
        """
        for record in self:
            record.amount = record.quantity * record.groupbuy_id.current_price

    def action_take(self):
        """Отметить, что заказ забран."""
        for record in self:
            if record.groupbuy_id.state != 'handout':
                raise UserError(_(
                    'Раздача ещё не началась — забирать нечего.'))
            record.state = 'taken'
        return True

    def action_cancel(self):
        """Отказаться от заказа.

        До «стопа» — свободно: участник передумал, объём пересчитается.
        После — нельзя: партия уже заказана у поставщика, и отказ одного
        означает, что за него платят остальные.
        """
        for record in self:
            if record.groupbuy_id.state != 'collecting':
                raise UserError(_(
                    'Сбор закрыт, партия заказана у поставщика. Отказ '
                    'сейчас означал бы, что за вас доплачивают остальные.'))
            record.state = 'cancelled'
        return True
