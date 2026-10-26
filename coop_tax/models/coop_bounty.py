# -*- coding: utf-8 -*-
from odoo import fields, models


class CoopBountyTask(models.Model):
    _inherit = 'coop.bounty.task'

    natural_income_ids = fields.One2many(
        'coop.tax.natural.income', 'task_id', string='НДФЛ с вознаграждения')
    natural_ndfl = fields.Monetary(
        string='НДФЛ с вознаграждения', currency_field='natural_currency_id',
        compute='_compute_natural_ndfl')
    natural_ndfl_state = fields.Selection(
        related='natural_income_ids.state', string='Состояние НДФЛ')
    natural_currency_id = fields.Many2one(
        'res.currency', compute='_compute_natural_ndfl')

    def _compute_natural_ndfl(self):
        rub = self.env.ref('base.RUB')
        for record in self:
            record.natural_ndfl = sum(record.natural_income_ids.mapped('ndfl_amount'))
            record.natural_currency_id = rub

    def action_accept(self):
        """Принятая задача, оплаченная токенами, — строка реестра (решение 515)."""
        result = super().action_accept()
        Income = self.env['coop.tax.natural.income'].sudo()
        # Исполнитель-организация — не НДФЛ (решение 553): реестр только людей.
        for record in self.filtered(lambda t: t.state == 'accepted'
                                    and t.payment_mode == 'tokens'
                                    and not t.assignee_id.is_company
                                    and t.payer_id and not t.natural_income_ids):
            Income._coop_register_task(record)
        return result
