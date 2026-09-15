# -*- coding: utf-8 -*-
"""Окно ставки.

Ставка — это число, и спросить его негде: в карточке торга полей для
ввода нет, а править саму запись аукциона участник не должен. Поэтому
окно: одно поле, подсказанное значение и кнопка.
"""

from odoo import _, api, fields, models


class CoopAuctionBidWizard(models.TransientModel):
    _name = 'coop.auction.bid.wizard'
    _description = 'Ставка на торге'

    auction_id = fields.Many2one(
        'coop.auction', string='Лот', required=True, readonly=True)
    kind = fields.Selection(related='auction_id.kind', readonly=True)
    currency_id = fields.Many2one(
        related='auction_id.currency_id', readonly=True)
    current_price = fields.Monetary(
        related='auction_id.current_price', readonly=True,
        string='Текущая цена', currency_field='currency_id')
    step = fields.Monetary(
        related='auction_id.step', readonly=True, string='Шаг торга',
        currency_field='currency_id')
    amount = fields.Monetary(
        string='Ваша ставка', currency_field='currency_id')

    @api.onchange('auction_id')
    def _onchange_auction_id(self):
        """Подсказать ближайшую допустимую ставку.

        Считать шаг в уме — лишняя работа, которую платформа может
        сделать за человека, а промах на рубль стоит отказа с ошибкой.
        """
        for wizard in self:
            if wizard.auction_id:
                wizard.amount = wizard.auction_id._suggested_bid()

    def action_place(self):
        self.ensure_one()
        self.auction_id._do_bid(self.amount)
        return {'type': 'ir.actions.act_window_close'}
