from odoo import fields, models


class RuBankCorracc(models.Model):
    _name = "ru.bank.corracc"
    _description = "Correspondent accounts of Russian banks"
    _rec_name = "corr_acc"

    bank_id = fields.Many2one(
        comodel_name="ru.bank", string="Bank", ondelete="cascade", index=True)
    corr_acc = fields.Char(
        string="Correspondent account",
        help="Correspondent account used by Russian banks",
    )
