from unittest.mock import MagicMock, patch

from odoo.exceptions import ValidationError
from odoo.tests.common import tagged

from .common import (
    DADATA_INDIVIDUAL_RESPONSE,
    DADATA_LEGAL_RESPONSE,
    DadataConnectorCommon,
)


@tagged("post_install", "-at_install")
class TestResPartnerDadata(DadataConnectorCommon):
    """Tests for res.partner DaData integration methods."""

    # ------------------------------------------------------------------
    # get_dadata_token
    # ------------------------------------------------------------------

    def test_get_dadata_token_returns_token(self):
        """Token is returned when the system parameter is set."""
        token = self.partner.get_dadata_token()
        self.assertEqual(token, "test_token_123")

    def test_get_dadata_token_raises_when_missing(self):
        """ValidationError is raised when token is not configured."""
        self.env["ir.config_parameter"].sudo().set_param(
            "dadata_connector.dadata_token", ""
        )
        with self.assertRaises(ValidationError):
            self.partner.get_dadata_token()

    # ------------------------------------------------------------------
    # _parse_dadata_response — legal entity
    # ------------------------------------------------------------------

    def test_parse_legal_entity_basic_fields(self):
        """Parsing a legal entity response fills basic partner fields."""
        wizard_data, result = self.partner._parse_dadata_response(DADATA_LEGAL_RESPONSE)

        self.assertEqual(result["vat"], "7707083893")
        self.assertEqual(result["ogrn"], "1027700132195")
        self.assertEqual(result["kpp"], "773601001")
        self.assertEqual(result["okpo"], "00032537")
        self.assertEqual(result["arceat"], "64.19")
        self.assertEqual(result["name"], "ПАО Сбербанк")
        self.assertEqual(result["city"], "Москва")
        self.assertEqual(result["zip"], "117997")
        self.assertEqual(result["street"], "ул Вавилова, дом, 19")

    def test_parse_legal_entity_company_form(self):
        """OPF code 12300 maps to 'plc' company form."""
        _, result = self.partner._parse_dadata_response(DADATA_LEGAL_RESPONSE)
        self.assertEqual(result["company_form"], "plc")

    def test_parse_legal_entity_wizard_data(self):
        """Wizard data contains status, organization_type, name and address."""
        wizard_data, _ = self.partner._parse_dadata_response(DADATA_LEGAL_RESPONSE)

        self.assertEqual(wizard_data["status"], "active")
        self.assertEqual(wizard_data["organization_type"], "legal")
        self.assertEqual(wizard_data["name"], "ПАО Сбербанк")
        self.assertIn("Вавилова", wizard_data["full_address"])

    def test_parse_legal_entity_management(self):
        """Management data is extracted when present."""
        _, result = self.partner._parse_dadata_response(DADATA_LEGAL_RESPONSE)

        self.assertIn("management", result)
        self.assertEqual(result["management"]["manager_name"], "ГРЕФ ГЕРМАН ОСКАРОВИЧ")
        self.assertEqual(
            result["management"]["manager_position"],
            "ПРЕЗИДЕНТ, ПРЕДСЕДАТЕЛЬ ПРАВЛЕНИЯ",
        )

    def test_parse_legal_entity_fts_registration(self):
        """FTS registration series and number are concatenated correctly."""
        _, result = self.partner._parse_dadata_response(DADATA_LEGAL_RESPONSE)
        self.assertEqual(result["sp_register_number"], "77 004599035")
        self.assertEqual(result["sp_register_date"], "2002-08-16")

    def test_parse_legal_entity_country_and_state(self):
        """Country and state are resolved from ISO codes when they exist in DB."""
        russia = self.env["res.country"].search([("code", "=", "RU")], limit=1)
        if not russia:
            self.skipTest("Russia not found in res.country — l10n data not loaded")

        _, result = self.partner._parse_dadata_response(DADATA_LEGAL_RESPONSE)
        self.assertEqual(result["country_id"][0], russia.id)

    # ------------------------------------------------------------------
    # _parse_dadata_response — individual entrepreneur
    # ------------------------------------------------------------------

    def test_parse_individual_name(self):
        """Individual entrepreneur name is built from fio parts."""
        _, result = self.partner._parse_dadata_response(DADATA_INDIVIDUAL_RESPONSE)
        self.assertEqual(result["name"], "ИВАНОВ ИВАН ИВАНОВИЧ")

    def test_parse_individual_no_kpp(self):
        """Individual entrepreneur response does not set kpp."""
        _, result = self.partner._parse_dadata_response(DADATA_INDIVIDUAL_RESPONSE)
        self.assertNotIn("kpp", result)

    def test_parse_individual_no_management(self):
        """No management key in result when management is absent."""
        _, result = self.partner._parse_dadata_response(DADATA_INDIVIDUAL_RESPONSE)
        self.assertNotIn("management", result)

    def test_parse_individual_no_fts_registration(self):
        """No sp_register_number when fts_registration is None."""
        _, result = self.partner._parse_dadata_response(DADATA_INDIVIDUAL_RESPONSE)
        self.assertNotIn("sp_register_number", result)

    # ------------------------------------------------------------------
    # get_legal_entity_data
    # ------------------------------------------------------------------

    @patch("myaddons.dob.dadata_connector.models.res_partner.Dadata")
    def test_get_legal_entity_data_returns_action(self, MockDadata):
        """get_legal_entity_data returns an act_window action when widget=True."""
        mock_instance = MagicMock()
        mock_instance.find_by_id.return_value = DADATA_LEGAL_RESPONSE
        MockDadata.return_value = mock_instance

        action = self.partner.get_legal_entity_data(vat="7707083893", widget=True)

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "res.partner.auto_data.wizard")
        self.assertEqual(action["target"], "new")

    @patch("myaddons.dob.dadata_connector.models.res_partner.Dadata")
    def test_get_legal_entity_data_returns_dict_when_no_widget(self, MockDadata):
        """get_legal_entity_data returns raw data dict when widget=False."""
        mock_instance = MagicMock()
        mock_instance.find_by_id.return_value = DADATA_LEGAL_RESPONSE
        MockDadata.return_value = mock_instance

        result = self.partner.get_legal_entity_data(vat="7707083893", widget=False)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["vat"], "7707083893")

    @patch("myaddons.dob.dadata_connector.models.res_partner.Dadata")
    def test_get_legal_entity_data_raises_when_empty(self, MockDadata):
        """ValidationError is raised when DaData returns no results."""
        mock_instance = MagicMock()
        mock_instance.find_by_id.return_value = []
        MockDadata.return_value = mock_instance

        with self.assertRaises(ValidationError):
            self.partner.get_legal_entity_data(vat="0000000000", widget=False)

    @patch("myaddons.dob.dadata_connector.models.res_partner.Dadata")
    def test_get_legal_entity_data_raises_on_http_error(self, MockDadata):
        """ValidationError is raised on HTTPStatusError from DaData."""
        from httpx import HTTPStatusError, Request, Response

        mock_instance = MagicMock()
        mock_instance.find_by_id.side_effect = HTTPStatusError(
            "401", request=MagicMock(spec=Request), response=MagicMock(spec=Response)
        )
        MockDadata.return_value = mock_instance

        with self.assertRaises(ValidationError):
            self.partner.get_legal_entity_data(vat="7707083893", widget=False)

    # ------------------------------------------------------------------
    # _get_view
    # ------------------------------------------------------------------

    def test_get_view_sets_dadata_search_widget_on_vat(self):
        """_get_view replaces widget on vat field with dadata_search."""
        arch, _view = self.env["res.partner"]._get_view(view_type="form")
        vat_nodes = arch.xpath("//field[@name='vat']")
        for node in vat_nodes:
            self.assertEqual(
                node.get("widget"),
                "dadata_search",
                "vat field must use dadata_search widget",
            )
