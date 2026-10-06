# -*- coding: utf-8 -*-
from odoo import api, models


class ContractCustomerReportOrder(models.AbstractModel):
    _name = 'contract.customer.report_order'
    _description = 'contract.customer.report_order'

  
    def get_report_values(self, docids, data=None):
        docs = self.env['sale.order'].browse(docids)
        return {
            'doc_ids': docs.ids,
            'doc_model': 'sale.order',
            'docs': docs,
        }



