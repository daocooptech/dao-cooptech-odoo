from odoo import fields, models


class Partner_Bank(models.Model):
    _inherit = 'res.partner.bank'
    bank_corr_acc = fields.Char('Кор.счет')