from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    company_registry = fields.Char(related='partner_id.coop_ogrn', readonly=False)
