# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoopTokenOrder(models.Model):
    """Заявка на бирже: продать или купить токены выпуска.

    Две разные вещи под одним названием, и различает их `kind`:

    - **первичная** — поставщик продаёт из своего выпуска. Цена задана при
      выпуске и не торгуется: сколько объявил, столько и стоит;
    - **вторичная** — держатель перепродаёт купленное до срока поставки.
      Здесь цену называет он сам, и она уже что-то значит. Если морковь
      подорожала, право получить её осенью стоит дороже, чем весной, и
      именно на вторичных заявках это становится видно.

    Расчёт — атомарный обмен: токены и деньги переходят одной транзакцией
    или не переходят вовсе. Ни продавец не отдаёт токены раньше денег, ни
    покупатель деньги раньше токенов, и доверять друг другу им не нужно.
    Платформа в расчёте не участвует и удержать ничего не может: она
    готовит параметры, подписывают стороны.

    Заявки не сводятся автоматически по цене: покупатель выбирает заявку
    сам и жмёт «купить». Это сознательное ограничение — автоматическое
    сведение встречных заявок по цене и есть организованные торги.
    """
    _name = 'coop.token.order'
    _description = 'Заявка на бирже токенов'
    _inherit = ['mail.thread']
    _order = 'price_per_unit, id'
    _rec_name = 'display_name'

    display_name = fields.Char(compute='_compute_display_name', store=True)

    claim_id = fields.Many2one(
        'coop.token.claim', string='Выпуск', required=True, index=True,
        ondelete='cascade')
    kind = fields.Selection([
        ('primary', 'Первичная продажа'),
        ('secondary', 'Перепродажа'),
    ], string='Вид заявки', required=True, default='secondary', index=True)
    side = fields.Selection([
        ('sell', 'Продажа'),
        ('buy', 'Покупка'),
    ], string='Сторона', required=True, default='sell', index=True,
        help='Заявка на покупку — это «куплю по такой цене, если кто-то '
             'готов продать». Она никого ни к чему не обязывает, пока '
             'держатель на неё не откликнулся.')

    partner_id = fields.Many2one(
        'res.partner', string='Кто выставил', required=True, index=True)

    quantity = fields.Float(string='Количество', required=True, digits=(16, 3))
    quantity_left = fields.Float(
        string='Осталось', digits=(16, 3), readonly=True,
        help='Заявку можно закрыть частями: покупателю нужна тонна, а в '
             'заявке двадцать.')
    price_per_unit = fields.Float(
        string='Цена за единицу', required=True, digits=(16, 4))
    total_price = fields.Float(
        string='Сумма', compute='_compute_total_price', store=True, digits=(16, 4))

    settlement_currency = fields.Selection(
        related='claim_id.settlement_currency', store=True, readonly=True)
    unit_label = fields.Char(related='claim_id.unit_label', readonly=True)
    delivery_date = fields.Date(
        related='claim_id.delivery_date', store=True, readonly=True)

    state = fields.Selection([
        ('draft', 'Черновик'),
        ('open', 'В стакане'),
        ('partial', 'Исполнена частично'),
        ('done', 'Исполнена'),
        ('cancelled', 'Снята'),
    ], string='Состояние', default='draft', required=True, index=True,
        tracking=True)

    trade_ids = fields.One2many('coop.token.trade', 'order_id', string='Сделки')

    # Наценка к цене выпуска — то, ради чего вторичный рынок и нужен:
    # по ней видно, дорожает обещание или дешевеет.
    premium_percent = fields.Float(
        string='К цене выпуска, %', compute='_compute_premium', store=True,
        digits=(5, 1))

    import_key = fields.Char(string='Ключ источника', index=True, copy=False)

    _quantity_positive = models.Constraint(
        'check(quantity > 0)',
        'Заявка на ноль единиц не имеет смысла.',
    )
    _price_positive = models.Constraint(
        'check(price_per_unit > 0)',
        'Цена за единицу должна быть больше нуля.',
    )

    @api.depends('claim_id.display_name', 'side', 'quantity', 'price_per_unit')
    def _compute_display_name(self):
        labels = {'sell': _('Продажа'), 'buy': _('Покупка')}
        for record in self:
            record.display_name = '%s %g × %g — %s' % (
                labels.get(record.side, ''),
                record.quantity,
                record.price_per_unit,
                record.claim_id.display_name or '',
            )

    @api.depends('quantity', 'price_per_unit')
    def _compute_total_price(self):
        for record in self:
            record.total_price = record.quantity * record.price_per_unit

    @api.depends('price_per_unit', 'claim_id.price_per_unit')
    def _compute_premium(self):
        for record in self:
            base = record.claim_id.price_per_unit
            record.premium_percent = (
                (record.price_per_unit - base) / base * 100 if base else 0.0)

    @api.constrains('quantity', 'claim_id', 'partner_id', 'side')
    def _check_seller_has_tokens(self):
        """Продавать можно только то, что есть на руках.

        Продажа без покрытия — это короткая позиция, и на рынке обещаний
        она означала бы торговлю тем, чего нет ни у кого. Проверка по
        нашему зеркалу балансов; последнее слово всё равно за сетью — она
        просто не проведёт перевод, которого нечем обеспечить.
        """
        for record in self:
            if record.side != 'sell' or record.kind == 'primary':
                continue
            holding = record.claim_id.holder_ids.filtered(
                lambda h: h.partner_id == record.partner_id)
            if not holding or holding.quantity < record.quantity:
                raise ValidationError(_(
                    'На руках меньше токенов, чем в заявке. Продать можно '
                    'только то, что куплено.'))

    def action_open(self):
        for record in self:
            if record.kind == 'primary' and record.partner_id != record.claim_id.issuer_id:
                raise UserError(_(
                    'Первичную продажу выставляет поставщик выпуска.'))
            if record.claim_id.state not in ('minted', 'trading'):
                raise UserError(_(
                    'Выпуск не торгуется: он ещё не выпущен, уже исполнен '
                    'или сорван.'))
            record.write({'state': 'open', 'quantity_left': record.quantity})
            record.claim_id.action_start_trading()
        return True

    def action_cancel(self):
        self.filtered(lambda r: r.state in ('draft', 'open', 'partial')).write(
            {'state': 'cancelled'})
        return True

    def action_prepare_trade(self, quantity=None):
        """Подготовить сделку по заявке.

        Именно подготовить: запись создаётся в состоянии «ждёт подписи», а
        переводит токены и деньги кошелёк покупателя. Пока транзакция не
        подтверждена сетью, сделка не считается состоявшейся — что бы ни
        было записано у нас.
        """
        self.ensure_one()
        if self.state not in ('open', 'partial'):
            raise UserError(_('Заявка снята или уже исполнена.'))
        me = self.env.user._coop_acting_partner()
        if me == self.partner_id:
            raise UserError(_('Это ваша собственная заявка.'))
        if not me.coop_ton_address:
            raise UserError(_(
                'Чтобы покупать и продавать токены, подключите кошелёк TON. '
                'Расчёт идёт между кошельками напрямую.'))
        amount = min(quantity or self.quantity_left, self.quantity_left)
        if amount <= 0:
            raise UserError(_('По заявке ничего не осталось.'))
        return self.env['coop.token.trade'].create({
            'order_id': self.id,
            'claim_id': self.claim_id.id,
            'seller_id': (self.partner_id if self.side == 'sell' else me).id,
            'buyer_id': (me if self.side == 'sell' else self.partner_id).id,
            'quantity': amount,
            'price_per_unit': self.price_per_unit,
        })


class CoopTokenTrade(models.Model):
    """Сделка обмена токенов на деньги.

    Живёт отдельно от заявки, потому что заявка исполняется частями и у
    одной заявки бывает несколько сделок с разными покупателями.

    Состояние отражает не намерение, а сеть: «ждёт подписи» — параметры
    готовы, «в сети» — транзакция отправлена, «исполнена» — сеть
    подтвердила. Считать сделку состоявшейся по записи в нашей базе
    нельзя: база знает лишь то, что ей сказали.
    """
    _name = 'coop.token.trade'
    _description = 'Сделка по токенам'
    _order = 'create_date desc, id desc'

    order_id = fields.Many2one(
        'coop.token.order', string='Заявка', required=True, index=True,
        ondelete='cascade')
    claim_id = fields.Many2one(
        'coop.token.claim', string='Выпуск', required=True, index=True)
    seller_id = fields.Many2one('res.partner', string='Продавец', required=True)
    buyer_id = fields.Many2one('res.partner', string='Покупатель', required=True)

    quantity = fields.Float(string='Количество', required=True, digits=(16, 3))
    price_per_unit = fields.Float(string='Цена за единицу', required=True, digits=(16, 4))
    total_price = fields.Float(
        string='Сумма', compute='_compute_total_price', store=True, digits=(16, 4))

    # Комиссия сети удерживается из суммы сделки — так участник не обязан
    # держать TON на кошельке, чтобы просто купить морковь.
    network_fee = fields.Float(
        string='Комиссия сети', digits=(16, 6), readonly=True,
        help='Газ TON, удержанный из суммы сделки.')

    state = fields.Selection([
        ('pending', 'Ждёт подписи'),
        ('sent', 'Отправлена в сеть'),
        ('done', 'Исполнена'),
        ('failed', 'Не прошла'),
    ], string='Состояние', default='pending', required=True, index=True)

    tx_hash = fields.Char(string='Транзакция', readonly=True, copy=False, index=True)
    confirmed_on = fields.Datetime(string='Подтверждена сетью', readonly=True)
    failure_reason = fields.Char(string='Почему не прошла', readonly=True)

    @api.depends('quantity', 'price_per_unit')
    def _compute_total_price(self):
        for record in self:
            record.total_price = record.quantity * record.price_per_unit

    def action_confirm_from_chain(self, tx_hash):
        """Отметить сделку исполненной по подтверждению сети.

        Вызывается после того, как транзакция найдена в блокчейне.
        Балансы в нашем зеркале двигаются здесь же: раньше двигать нечего,
        позже — значит показывать участнику вчерашний день.
        """
        self.ensure_one()
        self.write({
            'state': 'done',
            'tx_hash': tx_hash,
            'confirmed_on': fields.Datetime.now(),
        })
        self._move_holdings()
        self._open_escrow()
        order = self.order_id
        order.quantity_left = max(order.quantity_left - self.quantity, 0)
        order.state = 'done' if order.quantity_left <= 0 else 'partial'
        return True

    def _open_escrow(self):
        """Положить оплату покупателя в эскроу до поставки.

        Только для первичной продажи: там покупатель платит поставщику за
        товар, которого ещё нет. На вторичном рынке продавец — такой же
        держатель, товар ему никто не должен, и держать его деньги не за
        чем: он передаёт обещание, а не берёт на себя поставку.
        """
        Escrow = self.env['coop.token.escrow'].sudo()
        for record in self:
            if record.order_id.kind != 'primary':
                continue
            if Escrow.search_count([('trade_id', '=', record.id)]):
                continue
            Escrow.create({
                'trade_id': record.id,
                'buyer_id': record.buyer_id.id,
                'seller_id': record.seller_id.id,
                'amount': record.total_price,
                'quantity': record.quantity,
                'due_date': record.claim_id.delivery_date,
            })

    def _move_holdings(self):
        """Перенести токены между держателями в зеркале балансов."""
        Holding = self.env['coop.token.holding'].sudo()
        for record in self:
            buyer = Holding.search([
                ('claim_id', '=', record.claim_id.id),
                ('partner_id', '=', record.buyer_id.id)], limit=1)
            if buyer:
                buyer.quantity += record.quantity
            else:
                Holding.create({
                    'claim_id': record.claim_id.id,
                    'partner_id': record.buyer_id.id,
                    'quantity': record.quantity,
                })
            # У первичной продажи продавец — поставщик, и его «остаток»
            # считается от выпуска, а не хранится записью держателя.
            if record.order_id.kind == 'secondary':
                seller = Holding.search([
                    ('claim_id', '=', record.claim_id.id),
                    ('partner_id', '=', record.seller_id.id)], limit=1)
                if seller:
                    seller.quantity -= record.quantity
