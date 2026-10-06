from odoo import api, fields, models

class Bank(models.Model):
    _inherit = 'res.bank'

    corr_acc = fields.Char('Corresponding account', size=64)


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    bank_corr_acc = fields.Char('Corresponding account', size=64)

    @api.onchange('bank_id')
    def onchange_bank_id(self):
        for s in self:
            s.bank_name = s.bank_id.name
            s.bank_bic = s.bank_id.bic
            s.bank_corr_acc = s.bank_id.corr_acc
