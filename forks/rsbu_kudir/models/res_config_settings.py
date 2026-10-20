from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rsbu_usn_mode = fields.Selection(
        related='company_id.rsbu_usn_mode', readonly=False,
        string='Режим УСН')
    rsbu_accounting_start = fields.Date(
        related='company_id.rsbu_accounting_start', readonly=False,
        string='Дата начала учёта РСБУ')
