# -*- coding: utf-8 -*-
"""
Tests for l10n_ru_upd_xml — УПД XML generation.

Validates: Requirements 12.2, 12.4
"""
from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import UserError


def _make_company_partner(env):
    """Return or create a company partner with INN (10 digits) and KPP."""
    partner = env['res.partner'].search(
        [('is_company', '=', True), ('inn', '!=', False), ('kpp', '!=', False)],
        limit=1,
    )
    if not partner:
        partner = env['res.partner'].create({
            'name': 'ООО Тест УПД',
            'is_company': True,
            'inn': '7700000001',
            'kpp': '770001001',
            'okpo': '12345678',
            'city': 'Москва',
            'street': 'ул. Тестовая, 1',
        })
    return partner


def _make_out_invoice(env):
    """Create a minimal out_invoice with all fields required for УПД."""
    partner = _make_company_partner(env)

    journal = env['account.journal'].search(
        [('type', '=', 'sale'), ('company_id', '=', env.company.id)], limit=1
    )
    if not journal:
        journal = env['account.journal'].create({
            'name': 'Test Sales Journal UPD',
            'type': 'sale',
            'code': 'TUPD',
        })

    move = env['account.move'].create({
        'move_type': 'out_invoice',
        'partner_id': partner.id,
        'journal_id': journal.id,
        'invoice_date': '2024-06-01',
    })
    return move


@tagged('post_install', '-at_install')
class TestUpdXml(TransactionCase):
    """
    Tests for УПД XML generation.

    Validates: Requirements 12.2, 12.4
    """

    def setUp(self):
        super().setUp()
        self.invoice = _make_out_invoice(self.env)

    # ------------------------------------------------------------------
    # Requirement 12.2 — XML generation returns a valid XML document
    # ------------------------------------------------------------------

    def test_upd_xml_render_returns_valid_xml(self):
        """
        Req 12.2 — rendering the УПД XML QWeb template for an account.move
        returns non-empty bytes that parse as valid XML.
        """
        import xml.etree.ElementTree as ET

        xml_content, content_type = self.env['ir.actions.report']._render_qweb_xml(
            'l10n_ru_upd_xml.demo_report_xml_view', [self.invoice.id]
        )
        self.assertTrue(xml_content, "УПД XML render should return non-empty content")
        self.assertIsInstance(xml_content, bytes, "Rendered content should be bytes")

        # Must parse without exception — proves it is valid XML
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as exc:
            self.fail(f"Rendered УПД is not valid XML: {exc}")

        self.assertIsNotNone(root, "Parsed XML root element should not be None")

    # ------------------------------------------------------------------
    # Requirement 12.4 — missing INN/KPP raises UserError
    # ------------------------------------------------------------------

    def test_check_correct_upd_missing_inn_returns_error_message(self):
        """
        Req 12.4 — check_correct_upd on an account.move whose partner has no INN
        returns a non-empty error string mentioning the missing field.
        """
        partner_no_inn = self.env['res.partner'].create({
            'name': 'Партнёр без ИНН',
            'is_company': True,
            # inn intentionally omitted
        })
        journal = self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', self.env.company.id)], limit=1
        )
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner_no_inn.id,
            'journal_id': journal.id,
            'invoice_date': '2024-06-01',
        })

        error_msg = move.check_correct_upd(manually=False)
        self.assertTrue(
            error_msg.strip(),
            "check_correct_upd should return a non-empty error string when INN is missing",
        )
        self.assertIn('ИНН', error_msg, "Error message should mention ИНН")

    def test_print_upd_missing_inn_raises_user_error(self):
        """
        Req 12.4 — print_upd on an account.move whose partner has no INN
        raises UserError describing the missing fields.
        """
        partner_no_inn = self.env['res.partner'].create({
            'name': 'Партнёр без ИНН для print_upd',
            'is_company': True,
            # inn intentionally omitted
        })
        journal = self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', self.env.company.id)], limit=1
        )
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner_no_inn.id,
            'journal_id': journal.id,
            'invoice_date': '2024-06-01',
        })

        with self.assertRaises(UserError) as ctx:
            move.print_upd()

        self.assertIn('ИНН', str(ctx.exception),
                      "UserError message should mention ИНН")

    def test_print_upd_missing_kpp_raises_user_error(self):
        """
        Req 12.4 — print_upd on an account.move whose partner has INN (10 digits)
        but no KPP raises UserError describing the missing КПП.
        """
        partner_no_kpp = self.env['res.partner'].create({
            'name': 'Партнёр без КПП',
            'is_company': True,
            'inn': '7700000099',
            # kpp intentionally omitted
        })
        journal = self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', self.env.company.id)], limit=1
        )
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner_no_kpp.id,
            'journal_id': journal.id,
            'invoice_date': '2024-06-01',
        })

        with self.assertRaises(UserError) as ctx:
            move.print_upd()

        self.assertIn('КПП', str(ctx.exception),
                      "UserError message should mention КПП")
