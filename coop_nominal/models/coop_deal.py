# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

CHANNELS = [
    ('direct', 'Напрямую получателю'),
    ('nominal', 'Безопасная сделка: деньги на хранении до акта'),
]

# Стадии, на которых условия уже согласованы и деньги можно ждать.
AGREED = ('agreed', 'active', 'acceptance')


class CoopDeal(models.Model):
    """Безопасная сделка: деньги лежат на номинальном счёте до акта.

    Способ оплаты выбирается у сделки, позиции графика его наследуют, но
    каждую можно переключить. Удержания заводятся при согласовании: с
    этого момента у позиции есть код для назначения платежа.
    """
    _inherit = 'coop.deal'

    payment_channel = fields.Selection(
        CHANNELS, string='Способ оплаты', default='direct', required=True,
        tracking=True)
    nominal_hold_ids = fields.One2many(
        'coop.nominal.hold', 'deal_id', string='Платежи на удержании')

    def _coop_nominal_sync_holds(self):
        """Завести удержания по позициям «через номинальный счёт»."""
        Hold = self.env['coop.nominal.hold'].sudo()
        for record in self.filtered(lambda r: r.state in AGREED):
            lines = record.payment_ids.filtered(
                lambda p: p.channel == 'nominal' and not p.nominal_hold_id
                and p.state != 'cancelled' and p.amount > 0
                and p.payer_id and p.payee_id)
            if not lines:
                continue
            account = self.env['coop.nominal.account'].sudo().search(
                [('currency_id', '=', record.currency_id.id)], limit=1)
            if not account:
                raise UserError(_(
                    'Номинальный счёт в валюте сделки не заведён: оплатить '
                    'через него нельзя. Выберите оплату напрямую.'))
            Hold.create([{
                'account_id': account.id,
                'payment_id': line.id,
                'payer_id': line.payer_id.id,
                'payee_id': line.payee_id.id,
                'amount': line.amount,
            } for line in lines])
        return True

    def action_agree(self):
        result = super().action_agree()
        self._coop_nominal_sync_holds()
        return result

    def action_confirm_act(self):
        result = super().action_confirm_act()
        today = fields.Date.context_today(self)
        for record in self.filtered(lambda r: r.state == 'done'):
            holds = record.nominal_hold_ids.sudo()
            holds.filtered(lambda h: h.state in ('held_buyer', 'held_seller')
                           and not h.act_on)._act(today)
            # Акт и выплата в очередь — одна транзакция. Если реестр
            # расходится с выпиской, выплата подождёт сверки.
            for hold in holds.filtered(lambda h: h.state == 'held_seller'):
                if not hold.account_id.payouts_blocked:
                    hold._queue_payout()
        return result

    def action_open_dispute(self):
        result = super().action_open_dispute()
        self.nominal_hold_ids.sudo()._freeze()
        return result

    def action_resolve_dispute(self):
        result = super().action_resolve_dispute()
        self.nominal_hold_ids.sudo().filtered(
            lambda h: h.state == 'frozen')._unfreeze()
        return result

    def action_cancel(self):
        result = super().action_cancel()
        for hold in self.nominal_hold_ids.sudo():
            if hold.state == 'awaiting':
                hold._cancel()
            elif hold.state == 'held_buyer' and not hold.account_id.payouts_blocked:
                hold._queue_refund()
            # Деньги продавца без его согласия не возвращаются, а при
            # расхождении с выпиской возврат подождёт сверки.
        return result


class CoopDealPayment(models.Model):
    _inherit = 'coop.deal.payment'

    channel = fields.Selection(
        CHANNELS, string='Способ оплаты', compute='_compute_channel',
        store=True, readonly=False, required=True, precompute=True)
    nominal_hold_ids = fields.One2many(
        'coop.nominal.hold', 'payment_id', string='Удержания')
    nominal_hold_id = fields.Many2one(
        'coop.nominal.hold', string='Удержание',
        compute='_compute_nominal_hold')
    nominal_code = fields.Char(
        string='Код в назначении платежа', related='nominal_hold_id.code')

    @api.depends('deal_id.payment_channel')
    def _compute_channel(self):
        for record in self:
            record.channel = record.deal_id.payment_channel or 'direct'

    # Удержание на позицию одно (уникальность в базе), список — только
    # обратная сторона связи.
    @api.depends('nominal_hold_ids')
    def _compute_nominal_hold(self):
        for record in self:
            record.nominal_hold_id = record.sudo().nominal_hold_ids[:1]

    @api.model_create_multi
    def create(self, vals_list):
        payments = super().create(vals_list)
        payments.deal_id._coop_nominal_sync_holds()
        return payments

    def write(self, vals):
        if 'channel' in vals and self.sudo().filtered('nominal_hold_id'):
            raise UserError(_(
                'По позиции деньги уже на хранении: '
                'способ оплаты не меняется.'))
        result = super().write(vals)
        if 'channel' in vals:
            self.deal_id._coop_nominal_sync_holds()
        return result

    def action_mark_paid(self):
        """Оплату через номинальный счёт отмечает выписка, а не сторона."""
        if self.filtered(lambda p: p.channel == 'nominal'):
            raise UserError(_(
                'Оплата безопасной сделки отмечается по выписке банка, '
                'вручную её не ставят.'))
        return super().action_mark_paid()
