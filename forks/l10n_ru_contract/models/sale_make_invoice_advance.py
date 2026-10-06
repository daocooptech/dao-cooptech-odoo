from odoo import api, fields, models


class ContractCreateInvoice(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    # при выбора счета "Авансовый платеж"
    @api.model
    def _create_invoice(self, order, so_line, amount):
        res = super(ContractCreateInvoice, self)._create_invoice(order, so_line, amount)
        if order.mt_contract_id:
            res.write({'mt_contract_id': order.mt_contract_id,
                       'journal_id': order.mt_contract_id.profile_id.journal_id, })            
        return res
