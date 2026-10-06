# -*- coding: utf-8 -*-
from odoo import api, models


class ContractCustomerReportInvoice(models.AbstractModel):
    _name = 'contract.customer.report_invoice'

  
    def get_report_values(self, docids, data=None):
        docs = self.env['account.move'].browse(docids)
        return {
            'doc_ids': docs.ids,
            'doc_model': 'account.move',
            'docs': docs,
        }
