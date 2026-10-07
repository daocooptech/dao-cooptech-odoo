# -*- coding: utf-8 -*-
from odoo import models
from odoo.addons.l10n_ru_doc.report_helper import QWebHelper
class RuSaleOrderReport(models.AbstractModel):
    _name = 'report.l10n_ru_doc.report_order'
    _description = 'Печатная форма l10n_ru_doc.report_order'
    def _get_report_values(self, docids, data=None):
        docs = self.env['sale.order'].browse(docids)
        return {
            'helper': QWebHelper(),
            'doc_ids': docs.ids,
            'doc_model': 'sale.order',
            'docs': docs
        }
