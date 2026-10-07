from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dadata_token = fields.Char(
        string="DaData token",
        config_parameter="dadata_connector.dadata_token",
    )
