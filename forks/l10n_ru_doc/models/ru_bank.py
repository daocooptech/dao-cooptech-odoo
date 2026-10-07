from odoo import models


class RuBank(models.Model):
    _inherit = 'ru.bank'

    def _to_account_vals(self):
        vals = super()._to_account_vals()
        # the print forms read the correspondent account from the bank account
        vals['bank_corr_acc'] = self.corr_acc_ids[:1].corr_acc
        return vals
