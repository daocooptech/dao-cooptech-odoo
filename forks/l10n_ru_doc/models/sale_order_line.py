from odoo import models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _ru_print_name(self):
        """Text of the "Name" column of the print forms: no product code."""
        self.ensure_one()
        if not self.product_id or self.display_type:
            return self.name or ''
        product = self.product_id.with_context(lang=self.order_id._get_lang())
        return product._ru_print_name(self.name)
