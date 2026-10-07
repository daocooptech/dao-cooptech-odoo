from dadata import Dadata
from httpx import HTTPStatusError

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

okopf = {
    "50102": "sp",
    "11000": "pshp",
    "11051": "pshp",
    "11064": "pshp",
    "20700": "pshp",
    "20701": "pshp",
    "20716": "pshp",
    "30006": "pshp",
    # "": "coop",  # todo Cooperative
    "12300": "plc",
    "12200": "jsc",
    "12247": "pc",
    "12267": "сjsc",
    # "": "ga",  # todo Government agency
}


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == "form":
            for node in arch.xpath("//field[@name='vat']"):
                node.set("widget", "dadata_search")
        return arch, view

    def get_legal_entity_data(self, vat, widget=True):
        token = self.get_dadata_token()
        dadata = Dadata(token)
        try:
            result = dadata.find_by_id("party", vat, branch_type="MAIN")
        except HTTPStatusError:
            raise ValidationError(
                _(
                    "Failed to connect to DaData server. The token in the settings may be incorrect."
                )
            )

        if result:
            wizard_data, new_data = self._parse_dadata_response(result)

            if widget:
                wizard = self.env["res.partner.auto_data.wizard"].create(wizard_data)

                return {
                    "type": "ir.actions.act_window",
                    "target": "new",
                    "name": _("Set these details for the current contact?"),
                    "views": [(False, "form")],
                    "view_mode": "form",
                    "res_model": wizard._name,
                    "res_id": wizard.id,
                    "context": new_data,
                }
            else:
                return new_data
        else:
            raise ValidationError(_("No data found for the organization"))

    @api.model
    def get_dadata_token(self):
        token = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_str("dadata_connector.dadata_token")
        )
        if token:
            return token
        else:
            raise ValidationError(
                _(
                    "The token for DaData is not specified in the settings. (Settings - General settings - Integrations - DaData token)"
                )
            )

    def _parse_dadata_response(self, data):
        result = {}
        wizard_data = {}
        data = data[0]["data"]

        # Data for widget
        organization_type = data["type"].lower()
        wizard_data["partner_id"] = self.id
        wizard_data["status"] = data["state"]["status"].lower()
        wizard_data["organization_type"] = organization_type
        wizard_data["full_address"] = data["address"]["unrestricted_value"]

        # Data for partner
        result["vat"] = data["inn"]
        result["okpo"] = data["okpo"]
        result["arceat"] = data["okved"]
        result["company_form"] = okopf.get(data["opf"]["code"])
        result["ogrn"] = data["ogrn"]
        if data["documents"] and data["documents"]["fts_registration"]:
            result[
                "sp_register_number"
            ] = f'{data["documents"]["fts_registration"]["series"]} {data["documents"]["fts_registration"]["number"]}'
            result["sp_register_date"] = data["documents"]["fts_registration"][
                "issue_date"
            ]
        if organization_type == "legal":
            result["kpp"] = data["kpp"]

        # Name
        if organization_type == "legal":
            result["name"] = data["name"]["short_with_opf"]
            wizard_data["name"] = data["name"]["short_with_opf"]
        elif organization_type == "individual":
            result[
                "name"
            ] = f'{data["fio"]["surname"]} {data["fio"]["name"]} {data["fio"]["patronymic"]}'
            wizard_data[
                "name"
            ] = f'{data["fio"]["surname"]} {data["fio"]["name"]} {data["fio"]["patronymic"]}'
        else:
            raise ValidationError(_("Unknown organization type"))

        # Address
        address = data["address"]["data"]

        country = self.env["res.country"].search(
            [("code", "=", address["country_iso_code"])]
        )
        if country:
            result["country_id"] = country.id

            region = self.env["res.country.state"].search(
                [
                    ("code", "=", address["region_iso_code"].split("-")[-1]),
                    ("country_id", "=", country.id),
                ]
            )
            if region:
                result["state_id"] = region.id

        result["city"] = address["city"]
        street = []
        for el in [
            address["street_with_type"],
            address["house_type_full"],
            address["house"],
            address["flat_type_full"],
            address["flat"],
        ]:
            if el:
                street.append(el)
        result["street"] = ", ".join(street)
        result["zip"] = address["postal_code"]

        if data.get("management"):
            result["management"] = {
                "manager_name": data["management"]["name"],
                "manager_position": data["management"]["post"],
            }

        return wizard_data, result
