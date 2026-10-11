# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopNominalStatementResolve(models.TransientModel):
    """Ручной разбор нераспознанной строки выписки."""
    _name = 'coop.nominal.statement.resolve'
    _description = 'Разбор строки выписки'

    line_id = fields.Many2one(
        'coop.nominal.statement.line', string='Строка выписки', required=True,
        readonly=True)
    account_id = fields.Many2one(related='line_id.account_id')
    direction = fields.Selection(related='line_id.direction')
    amount = fields.Monetary(related='line_id.amount')
    currency_id = fields.Many2one(related='line_id.currency_id')
    purpose = fields.Char(related='line_id.purpose')
    partner_name = fields.Char(related='line_id.partner_name')
    mode = fields.Selection([
        ('holds', 'Это оплата платежей на удержании'),
        ('refund', 'Вернуть отправителю'),
        ('payout', 'Это выплата из реестра'),
        ('offset', 'Гасится встречной строкой'),
    ], string='Что это', required=True, compute='_compute_mode', store=True, precompute=True,
        readonly=False)
    hold_ids = fields.Many2many(
        'coop.nominal.hold', string='Платежи на удержании')
    payout_id = fields.Many2one('coop.nominal.payout', string='Выплата')
    counterpart_line_id = fields.Many2one(
        'coop.nominal.statement.line', string='Встречная строка')

    @api.depends('direction')
    def _compute_mode(self):
        for record in self:
            record.mode = 'holds' if record.direction == 'in' else 'payout'

    def action_apply(self):
        self.ensure_one()
        line = self.line_id
        allowed = {'in': ('holds', 'refund', 'offset'), 'out': ('payout', 'offset')}
        if self.mode not in allowed[line.direction]:
            raise UserError(_('Для этого движения такой разбор не подходит.'))
        if self.mode == 'holds':
            line._resolve_holds(self.hold_ids)
        elif self.mode == 'refund':
            line._resolve_refund()
        elif self.mode == 'payout':
            line._resolve_payout(self.payout_id)
        else:
            line._resolve_offset(self.counterpart_line_id)
        return {'type': 'ir.actions.act_window_close'}
