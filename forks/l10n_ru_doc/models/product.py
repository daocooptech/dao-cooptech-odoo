from odoo import fields, models

class ProductTnved(models.Model):
    _inherit = 'product.product'
    kod_tnved = fields.Char('Код ТНВЭД')
