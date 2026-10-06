from odoo import models, fields, api, _


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    uom_okei = fields.Char(string='Код ОКЕИ', related='product_uom_id.okei')
