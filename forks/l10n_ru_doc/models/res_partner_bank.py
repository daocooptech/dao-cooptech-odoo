from odoo import fields, models


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    bank_corr_acc = fields.Char('Corresponding account', size=64)


