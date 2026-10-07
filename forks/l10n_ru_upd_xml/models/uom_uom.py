from odoo import  fields, models, _


class UomUom(models.Model):
    _inherit = "uom.uom"

    okei = fields.Char(string="Код ОКЕИ")
