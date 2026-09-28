from odoo import models, fields


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    prepaid_ids = fields.Many2many('order.prepaid.line', string='Связные строки авансовых счетов')
    bool_const_bill = fields.Boolean(copy=False)
    bool_const_bill_bill = fields.Boolean(copy=False)