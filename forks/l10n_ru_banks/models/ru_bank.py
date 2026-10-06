from odoo import api, fields, models


class RuBank(models.Model):
    """Directory of Russian banks (tip directory).

    Odoo 20 has no `res.bank`: bank details live in `res.partner.bank` itself.
    The directory is not referenced by documents. A bank chosen on an account
    copies its details into the account fields (see `res.partner.bank`), and
    print forms read only those fields.
    """
    _name = "ru.bank"
    _description = "Russian Banks"
    _order = "name"
    _rec_names_search = ["name", "bic"]

    name = fields.Char(required=True)
    street = fields.Char()
    street2 = fields.Char()
    zip = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one(
        "res.country.state", string="Fed. State",
        domain="[('country_id', '=?', country_id)]")
    country_id = fields.Many2one("res.country")
    email = fields.Char()
    phone = fields.Char()
    active = fields.Boolean(default=True)
    bic = fields.Char(
        string="Bank Identifier Code", index=True,
        help="Sometimes called BIC or Swift.")
    corr_acc_ids = fields.One2many(
        comodel_name="ru.bank.corracc",
        inverse_name="bank_id",
        string="Correspondent accounts",
    )
    country_code = fields.Char(related="country_id.code")

    @api.depends("name", "bic")
    def _compute_display_name(self):
        for bank in self:
            bank.display_name = f"{bank.name} ({bank.bic})" if bank.bic else bank.name

    def _to_account_vals(self):
        """Values copied into `res.partner.bank` when this bank is chosen."""
        self.ensure_one()
        return {
            "bank_name": self.name,
            "bank_bic": self.bic,
            "street": self.street,
            "street2": self.street2,
            "zip": self.zip,
            "city": self.city,
            "state_id": self.state_id.id,
            "country_id": self.country_id.id,
        }
