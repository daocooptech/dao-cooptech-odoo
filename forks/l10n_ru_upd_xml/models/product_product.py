from odoo import models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def get_hs_code(self):
        """Код ТН ВЭД для УПД: поле hs_code принадлежит stock_delivery."""
        self.ensure_one()
        return self.hs_code or ""
