# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class CoopWalletNominal(models.Model):
    """Фиатная вкладка: безопасные сделки участника на номинальном счёте.

    Цифры — из книги счёта, а не из состояний удержаний: остаток
    бенефициара в книге — это и есть его деньги на счёте.
    """
    _inherit = 'coop.wallet'

    nominal_hold_ids = fields.Many2many(
        'coop.nominal.hold', string='Безопасные сделки',
        compute='_compute_nominal')
    nominal_hold_count = fields.Integer(
        string='Платежей на удержании', compute='_compute_nominal')
    nominal_to_pay = fields.Monetary(
        string='Внести на хранение', currency_field='currency_id',
        compute='_compute_nominal',
        help='Платежи по графикам, которых счёт ещё не получил. В назначении '
             'платежа — код удержания (CT-…), по нему банк найдёт сделку.')
    nominal_mine_before_act = fields.Monetary(
        string='Мои деньги до акта', currency_field='currency_id',
        compute='_compute_nominal',
        help='Вы заплатили, акта ещё нет: деньги на хранении в банке и '
             'принадлежат вам. Подпишете акт — перейдут продавцу.')
    nominal_mine_to_receive = fields.Monetary(
        string='Ждёт выплаты мне', currency_field='currency_id',
        compute='_compute_nominal',
        help='Акт подписан, деньги ваши за вычетом комиссии оператора: банк '
             'переводит их на ваш счёт.')

    @api.depends('partner_id')
    def _compute_nominal(self):
        Hold = self.env['coop.nominal.hold']
        Entry = self.env['coop.nominal.entry']
        for wallet in self:
            partner = wallet.partner_id
            holds = Hold.search([
                '|', ('payer_id', '=', partner.id), ('payee_id', '=', partner.id),
            ]) if partner else Hold
            wallet.nominal_hold_ids = holds
            wallet.nominal_hold_count = len(holds)
            wallet.nominal_to_pay = sum(holds.filtered(
                lambda h: h.payer_id == partner and h.state == 'awaiting').mapped('amount'))
            # Остаток бенефициара — минус сумма его записей.
            balance = {
                hold.id: -amount for hold, amount in Entry.sudo()._read_group(
                    [('leg', '=', 'holder'), ('partner_id', '=', partner.id),
                     ('hold_id', 'in', holds.ids)],
                    groupby=['hold_id'], aggregates=['amount:sum'])
            } if holds else {}
            wallet.nominal_mine_before_act = sum(
                balance.get(h.id, 0.0) for h in holds if h.payer_id == partner)
            wallet.nominal_mine_to_receive = sum(
                balance.get(h.id, 0.0) for h in holds if h.payee_id == partner)

    def action_nominal_statement(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Выписка по безопасным сделкам'),
            'res_model': 'coop.nominal.partner.statement',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_wallet_id': self.id},
        }
