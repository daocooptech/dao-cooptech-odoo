# -*- coding: utf-8 -*-
from odoo import api, models

class ContractCustomerReport(models.AbstractModel):
    _name = 'contract.customer.report'
    _description = 'contract.customer.report'

  
    def get_report_values(self, docids, data=None):
        docs = self.env['partner.contract.customer'].browse(docids)
        return {
            'doc_ids': docs.ids,
            'doc_model': 'partner.contract.customer',
            'docs': docs,
        }
