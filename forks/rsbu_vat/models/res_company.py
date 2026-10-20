from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # rsbu_vat_mode перенесён в rsbu_kudir (его читает КУДиР).
