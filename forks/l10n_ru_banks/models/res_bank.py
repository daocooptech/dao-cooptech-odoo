from odoo import api, fields, models


class ResBankCorrAcc(models.Model):
    _name = "res.bank.corracc"
    _description = "Correspondent accounts of Russian banks"
    _rec_name = "corr_acc"

    bank_id = fields.Many2one(comodel_name="res.bank", string="Bank")

    corr_acc = fields.Char(
        string="Correspondent account",
        help="Correspondent account used by Russian banks",
    )


class ResBank(models.Model):
    # ПРОВИЗОРНО (Э5, 06.10.2026): в Odoo 20 модели res.bank в ядре нет - банковские
    # реквизиты живут прямо в res.partner.bank (bank_name, bank_bic, street...).
    # Справочник банков и ссылка res.partner.bank.bank_id воссозданы здесь, чтобы
    # цепочка l10n_ru_* и печатные формы (bank_id.name/street/bic) работали как в 19.
    # Решение, оставлять ли справочник, - за основной сессией.
    _name = "res.bank"
    _description = "Russian Banks"
    _order = "name"
    _rec_names_search = ("name", "bic")

    name = fields.Char(required=True)
    street = fields.Char()
    street2 = fields.Char()
    zip = fields.Char()
    city = fields.Char()
    state = fields.Many2one("res.country.state", string="Fed. State",
                            domain="[('country_id', '=?', country)]")
    country = fields.Many2one("res.country")
    email = fields.Char()
    phone = fields.Char()
    active = fields.Boolean(default=True)
    bic = fields.Char(string="Bank Identifier Code", index=True,
                      help="Sometimes called BIC or Swift.")
    corr_acc_ids = fields.One2many(
        comodel_name="res.bank.corracc",
        inverse_name="bank_id",
        string="Correspondent accounts",
    )

    country_code = fields.Char(related="country.code", store=False)


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    bank_id = fields.Many2one("res.bank", string="Bank")

    @api.onchange("bank_id")
    def onchange_bank_id(self):
        self.bank_name = self.bank_id.name
        self.bank_bic = self.bank_id.bic
