from datetime import datetime
from odoo import api, fields, models

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    price_total_pf = fields.Monetary(
        string='TotalPF',
        compute='_compute_totals',
        currency_field='currency_id',
    )

    @api.depends('quantity', 'discount', 'price_unit', 'tax_ids', 'currency_id')
    def _compute_totals(self):
        super(AccountMoveLine,self)._compute_totals()
        for line in self:
            line_discount_price_unit = line.price_unit * (1 - (line.discount / 100.0))
            if line.tax_ids.filtered(lambda tax: tax.invisiblePF == False):
                taxes_res = line.tax_ids.filtered(lambda tax: tax.invisiblePF == False).compute_all(
                    line_discount_price_unit,
                    quantity=line.quantity,
                    currency=line.currency_id,
                    product=line.product_id,
                    partner=line.partner_id,
                    is_refund=line.is_refund,
                )
                line.price_total_pf = taxes_res['total_included']
            else:
                line.price_total_pf = line.price_total