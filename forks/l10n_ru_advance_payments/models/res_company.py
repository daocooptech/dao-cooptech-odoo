from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    advance_out_id = fields.Many2one(comodel_name='account.account', string='Исходящий счет')
    advance_in_id = fields.Many2one(comodel_name='account.account', string='Входящий счет')