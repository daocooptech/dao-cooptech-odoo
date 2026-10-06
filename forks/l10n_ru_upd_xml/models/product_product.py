from odoo import models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def get_hs_code(self):
        """Код ТН ВЭД для УПД.

        В Odoo 20 поле hs_code принадлежит модулю stock_delivery, а не продукту;
        от stock_delivery этот модуль не зависит, поэтому поле читается, только
        если оно есть.
        """
        self.ensure_one()
        return self.hs_code if "hs_code" in self._fields else ""
