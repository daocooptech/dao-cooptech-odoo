# -*- coding: utf-8 -*-
"""
Tests for l10n_ru_doc report generation.

Validates: Requirement 12.1
"""
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


def _make_out_invoice(env):
    """Create a minimal out_invoice account.move for report testing."""
    partner = env['res.partner'].search([('is_company', '=', True)], limit=1)
    if not partner:
        partner = env['res.partner'].create({'name': 'Test Partner RU', 'is_company': True})

    journal = env['account.journal'].search(
        [('type', '=', 'sale'), ('company_id', '=', env.company.id)], limit=1
    )
    if not journal:
        journal = env['account.journal'].create({
            'name': 'Test Sales Journal',
            'type': 'sale',
            'code': 'TSALE',
        })

    move = env['account.move'].create({
        'move_type': 'out_invoice',
        'partner_id': partner.id,
        'journal_id': journal.id,
        'invoice_date': '2024-01-15',
    })
    return move


@tagged('post_install', '-at_install')
class TestRuDoc(TransactionCase):
    """
    Validates: Requirement 12.1 — ТОРГ-12 report generation for out_invoice
    returns non-empty binary content without exceptions.
    """

    def setUp(self):
        super().setUp()
        self.invoice = _make_out_invoice(self.env)

    def test_torg12_report_values_no_exception(self):
        """
        Req 12.1 — calling _get_report_values on the ТОРГ-12 report model
        for an out_invoice returns a non-empty dict without exceptions.
        """
        report_model = self.env['report.l10n_ru_doc.report_bill']
        result = report_model._get_report_values([self.invoice.id])
        self.assertIsInstance(result, dict, "Report values should be a dict")
        self.assertIn('docs', result, "Report values should contain 'docs' key")
        self.assertTrue(result['docs'], "Report docs should be non-empty")

    def test_torg12_html_render_returns_binary_content(self):
        """
        Req 12.1 — rendering the ТОРГ-12 QWeb template for an out_invoice
        returns non-empty binary content without exceptions.
        """
        html_content, content_type = self.env['ir.actions.report']._render_qweb_html(
            'l10n_ru_doc.report_bill', [self.invoice.id]
        )
        self.assertTrue(html_content, "ТОРГ-12 HTML render should return non-empty binary content")
        self.assertIsInstance(html_content, bytes, "Rendered content should be bytes")
        self.assertGreater(len(html_content), 0, "Rendered content should have non-zero length")

    def test_torg12_report_values_contains_helper(self):
        """
        Req 12.1 — report values include the QWebHelper instance for formatting.
        """
        report_model = self.env['report.l10n_ru_doc.report_bill']
        result = report_model._get_report_values([self.invoice.id])
        self.assertIn('helper', result, "Report values should contain 'helper' key")
        self.assertIsNotNone(result['helper'], "Helper should not be None")
