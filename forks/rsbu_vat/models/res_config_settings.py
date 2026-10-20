from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rsbu_vat_mode = fields.Selection(
        related='company_id.rsbu_vat_mode', readonly=False,
        string='Режим НДС на УСН')
