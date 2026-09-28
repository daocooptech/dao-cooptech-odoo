from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    advance_out_id = fields.Many2one(comodel_name='account.account', string='Исходящий счет', related='company_id.advance_out_id',readonly=False)
    advance_in_id = fields.Many2one(comodel_name='account.account', string='Входящий счет', related='company_id.advance_in_id',readonly=False)






