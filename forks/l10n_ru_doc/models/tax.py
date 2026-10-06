from odoo import fields, models

class TaxInherit(models.Model):
    _inherit = 'account.tax'

    invisiblePF = fields.Boolean('Не видно в ПФ')
