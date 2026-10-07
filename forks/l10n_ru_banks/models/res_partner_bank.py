from odoo import api, fields, models


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    ru_bank_id = fields.Many2one(
        "ru.bank", string="Bank from directory",
        help="A tip only: choosing a bank copies its details into the fields "
             "of this account. Documents read the account, not the directory.")

    @api.onchange("ru_bank_id")
    def _onchange_ru_bank_id(self):
        for account in self.filtered("ru_bank_id"):
            for fname, value in account.ru_bank_id._to_account_vals().items():
                account[fname] = value

    @api.model_create_multi
    def create(self, vals_list):
        # an account created from code or import with a chosen bank gets the
        # bank details unless the caller has set them explicitly
        for vals in vals_list:
            if vals.get("ru_bank_id"):
                bank = self.env["ru.bank"].browse(vals["ru_bank_id"])
                for fname, value in bank._to_account_vals().items():
                    if value:
                        vals.setdefault(fname, value)
        return super().create(vals_list)
