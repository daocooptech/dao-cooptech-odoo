from odoo import models


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'rsbu.posting.mixin']

    def action_post(self):
        res = super().action_post()
        for move in self.filtered(lambda m: m.state == 'posted'):
            move._rsbu_generate()
        return res

    def button_draft(self):
        self._rsbu_remove()
        return super().button_draft()

    def button_cancel(self):
        self._rsbu_remove()
        return super().button_cancel()
