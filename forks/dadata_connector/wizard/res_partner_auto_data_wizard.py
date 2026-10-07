from odoo import fields, models


class ResPartnerAutoDataWizard(models.TransientModel):
    _name = "res.partner.auto_data.wizard"
    _description = "Wizard for autofilling partner"

    partner_id = fields.Many2one(
        string="Partner",
        comodel_name="res.partner",
    )

    vat = fields.Char(
        string="Identification Number", help="Identification Number for selected type"
    )

    status = fields.Selection(
        string="Status",
        selection=[
            ("active", "Active"),
            ("liquidating", "Liquidating"),
            ("liquidated", "Liquidated"),
            ("bankrupt", "Bankrupt"),
            ("reorganizing", "Reorganizing"),
        ],
    )
    organization_type = fields.Selection(
        string="Type of organization",
        selection=[
            ("legal", "Legal entity"),
            ("individual", "Individual entrepreneur"),
        ],
        help="Legal entity or individual entrepreneur",
    )
    name = fields.Char(string="Full name")

    full_address = fields.Text(string="Full legal address")

    def button_yes(self):
        return {"type": "ir.actions.act_window_close", "infos": {"update": True}}
