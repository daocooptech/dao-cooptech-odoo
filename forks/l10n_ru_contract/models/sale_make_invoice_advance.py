from odoo import models


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    def _prepare_down_payment_invoice_values(self, order, so_lines, accounts):
        """Счёт «Авансовый платёж» ведётся в журнале, который указан в виде договора."""
        invoice_vals = super()._prepare_down_payment_invoice_values(order, so_lines, accounts)
        journal = order.mt_contract_id.profile_id.journal_id
        if journal:
            invoice_vals['journal_id'] = journal.id
        return invoice_vals
