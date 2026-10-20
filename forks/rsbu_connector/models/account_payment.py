from odoo import models


class AccountPayment(models.Model):
    _name = 'account.payment'
    _inherit = ['account.payment', 'rsbu.posting.mixin']

    def action_post(self):
        res = super().action_post()
        # После проведения платёж переходит в in_process или paid.
        for payment in self.filtered(lambda p: p.state in ('in_process', 'paid')):
            payment._rsbu_generate()
        return res

    def action_draft(self):
        self._rsbu_remove()
        return super().action_draft()

    def action_cancel(self):
        self._rsbu_remove()
        return super().action_cancel()
