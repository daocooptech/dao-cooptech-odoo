from odoo.tests.common import tagged

from .common import DadataConnectorCommon


@tagged("post_install", "-at_install")
class TestResPartnerAutoDataWizard(DadataConnectorCommon):
    """Tests for res.partner.auto_data.wizard."""

    def _create_wizard(self, **kwargs):
        vals = {
            "partner_id": self.partner.id,
            "name": "ПАО Тест",
            "status": "active",
            "organization_type": "legal",
            "full_address": "117997, г Москва, ул Вавилова, д 19",
        }
        vals.update(kwargs)
        return self.env["res.partner.auto_data.wizard"].create(vals)

    def test_wizard_creation(self):
        """Wizard record is created with expected field values."""
        wizard = self._create_wizard()
        self.assertEqual(wizard.name, "ПАО Тест")
        self.assertEqual(wizard.status, "active")
        self.assertEqual(wizard.organization_type, "legal")
        self.assertEqual(wizard.partner_id, self.partner)

    def test_button_yes_returns_close_action(self):
        """button_yes returns act_window_close with update flag."""
        wizard = self._create_wizard()
        result = wizard.button_yes()

        self.assertEqual(result["type"], "ir.actions.act_window_close")
        self.assertTrue(result["infos"]["update"])

    def test_wizard_status_selection_values(self):
        """All expected status values are accepted."""
        statuses = ["active", "liquidating", "liquidated", "bankrupt", "reorganizing"]
        for status in statuses:
            wizard = self._create_wizard(status=status)
            self.assertEqual(wizard.status, status)

    def test_wizard_organization_type_individual(self):
        """Wizard accepts individual organization type."""
        wizard = self._create_wizard(organization_type="individual")
        self.assertEqual(wizard.organization_type, "individual")
