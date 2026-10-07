# -*- coding: utf-8 -*-
from odoo import models
from odoo.addons.l10n_ru_advance_payments.report_helper import QWebHelper


class RuOrderPrepaidReport(models.AbstractModel):
    _name = 'report.l10n_ru_advance_payments.report_order_prepaid'
    _description = 'Печатная форма l10n_ru_advance_payments.report_order_prepaid'

    def _get_report_values(self, docids, data=None):
        docs = self.env['order.prepaid'].browse(docids)
        return {
            'helper': QWebHelper(),
            'doc_ids': docs.ids,
            'doc_model': 'order.prepaid',
            'docs': docs
        }
