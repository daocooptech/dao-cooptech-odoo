from odoo import fields, models, _


class AccountAccount(models.Model):
    _inherit = "account.account"

    centralized = fields.Boolean("Централизованно")
