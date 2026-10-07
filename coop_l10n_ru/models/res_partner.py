from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # The chain l10n_ru_* declares both as stored Char fields; here they only
    # read and write the platform field, so OGRN lives in one place.
    ogrn = fields.Char(related='coop_ogrn', readonly=False)
    company_registry = fields.Char(related='coop_ogrn', readonly=False)
