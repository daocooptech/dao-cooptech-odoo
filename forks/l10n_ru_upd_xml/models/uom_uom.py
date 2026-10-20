from odoo import  fields, models


class UomUom(models.Model):
    _inherit = "uom.uom"

    okei = fields.Char(string="Код ОКЕИ")
