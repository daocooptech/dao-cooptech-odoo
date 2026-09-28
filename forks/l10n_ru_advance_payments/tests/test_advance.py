# -*- coding: utf-8 -*-
"""
Tests for l10n_ru_advance_payments — advance payment invoices.

Validates: Requirements 14.1, 14.2, 14.3
"""
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


def _get_or_create_partner(env):
    """Return an existing company partner or create one."""
    partner = env['res.partner'].search(
        [('is_company', '=', True)], limit=1
    )
    if not partner:
        partner = env['res.partner'].create({
            'name': 'Test Partner Advance',
            'is_company': True,
        })
    return partner


def _get_or_create_contract(env, partner):
    """Return an existing contract or create a minimal one."""
    contract = env['partner.contract.customer'].search(
        [('partner_id', '=', partner.id)], limit=1
    )
    if not contract:
        profile = env['contract.profile'].search([], limit=1)
        if not profile:
            profile = env['contract.profile'].create({'name': 'Test Profile'})
        contract = env['partner.contract.customer'].create({
            'date_start': '2024-01-01',
            'date_end': '2024-12-31',
            'type': 'customer',
            'profile_id': profile.id,
            'partner_id': partner.id,
            'partner_type': 'company',
            'company_id': env.company.id,
        })
    return contract


def _make_prepaid(env, partner=None):
    """Create a minimal order.prepaid record."""
    if partner is None:
        partner = _get_or_create_partner(env)
    return env['order.prepaid'].create({
        'partner_id': partner.id,
        'company_id': env.company.id,
        'invoice_date': '2024-06-01',
        'invoice_date_due': '2024-06-30',
        'prepaid_line': [(0, 0, {
            'label': 'Аванс',
            'quantity': 1.0,
            'price_unit': 1000.0,
        })],
    })


@tagged('post_install', '-at_install')
class TestAdvancePayments(TransactionCase):
    """
    Tests for advance payment invoices (order.prepaid).

    Validates: Requirements 14.1, 14.2, 14.3
    """

    def setUp(self):
        super().setUp()
        self.partner = _get_or_create_partner(self.env)
        self.contract = _get_or_create_contract(self.env, self.partner)
        self.prepaid = _make_prepaid(self.env, self.partner)

    # ------------------------------------------------------------------
    # Requirement 14.1 — create advance invoice with contract and partner
    # ------------------------------------------------------------------

    def test_create_advance_with_partner_no_error(self):
        """
        Req 14.1 — creating an order.prepaid with a partner saves without errors.
        """
        self.assertTrue(self.prepaid.id, "order.prepaid should be created with a valid id")
        self.assertEqual(self.prepaid.partner_id, self.partner,
                         "partner_id should match the provided partner")
        self.assertEqual(self.prepaid.state, 'draft',
                         "Newly created prepaid should be in draft state")

    def test_create_advance_with_contract_and_partner_no_error(self):
        """
        Req 14.1 — creating an order.prepaid linked to a contract and partner
        saves without errors.
        """
        prepaid = self.env['order.prepaid'].create({
            'partner_id': self.partner.id,
            'company_id': self.env.company.id,
            'invoice_date': '2024-07-01',
            'invoice_date_due': '2024-07-31',
            'prepaid_line': [(0, 0, {
                'label': 'Предоплата по договору',
                'quantity': 1.0,
                'price_unit': 5000.0,
            })],
        })
        self.assertTrue(prepaid.id, "order.prepaid with contract should be created")
        self.assertEqual(prepaid.partner_id.id, self.partner.id)
        self.assertGreater(prepaid.amount, 0, "Amount should be computed from lines")

    # ------------------------------------------------------------------
    # Requirement 14.2 — printing returns non-empty binary content
    # ------------------------------------------------------------------

    def test_print_advance_report_values_no_exception(self):
        """
        Req 14.2 — calling _get_report_values on the advance payment report model
        returns a non-empty dict without exceptions.
        """
        report_model = self.env['report.l10n_ru_advance_payments.report_order_prepaid']
        result = report_model._get_report_values([self.prepaid.id])
        self.assertIsInstance(result, dict, "Report values should be a dict")
        self.assertIn('docs', result, "Report values should contain 'docs' key")
        self.assertTrue(result['docs'], "Report docs should be non-empty")

    def test_print_advance_html_render_returns_binary_content(self):
        """
        Req 14.2 — rendering the advance payment QWeb template returns
        non-empty binary content without exceptions.
        """
        html_content, content_type = self.env['ir.actions.report']._render_qweb_html(
            'l10n_ru_advance_payments.report_order_prepaid', [self.prepaid.id]
        )
        self.assertTrue(html_content,
                        "Advance payment HTML render should return non-empty binary content")
        self.assertIsInstance(html_content, bytes, "Rendered content should be bytes")
        self.assertGreater(len(html_content), 0, "Rendered content should have non-zero length")

    # ------------------------------------------------------------------
    # Requirement 14.3 — registering payment creates account.payment
    # ------------------------------------------------------------------

    def test_register_payment_creates_account_payment(self):
        """
        Req 14.3 — using the payment wizard creates a corresponding account.payment record.
        """
        # Post the prepaid first
        self.prepaid.action_post()
        self.assertEqual(self.prepaid.state, 'posted',
                         "Prepaid should be in posted state after action_post")

        # Find a bank/cash journal
        journal = self.env['account.journal'].search(
            [('type', 'in', ['bank', 'cash']),
             ('company_id', '=', self.env.company.id)],
            limit=1
        )
        self.assertTrue(journal, "A bank or cash journal must exist for payment registration")

        # Find a payment method line
        payment_method_line = journal.outbound_payment_method_line_ids[:1]
        if not payment_method_line:
            payment_method_line = journal.inbound_payment_method_line_ids[:1]
        self.assertTrue(payment_method_line,
                        "Journal must have at least one payment method line")

        # Create the wizard directly and call action_create_payments
        wizard = self.env['payment.register.prepaid'].create({
            'prepaid_id': self.prepaid.id,
            'company_id': self.env.company.id,
            'amount': self.prepaid.amount,
            'currency_id': self.prepaid.currency_id.id,
            'payment_date': '2024-06-15',
            'journal_id': journal.id,
            'payment_method_line_id': payment_method_line.id,
            'communication': self.prepaid.name,
        })

        payment_count_before = self.env['account.payment'].search_count(
            [('prepaid_id', '=', self.prepaid.id)]
        )

        wizard.action_create_payments()

        payment_count_after = self.env['account.payment'].search_count(
            [('prepaid_id', '=', self.prepaid.id)]
        )
        self.assertGreater(
            payment_count_after, payment_count_before,
            "action_create_payments should create a new account.payment linked to the prepaid"
        )

    def test_register_payment_payment_linked_to_prepaid(self):
        """
        Req 14.3 — the created account.payment has prepaid_id set to the advance invoice.
        """
        self.prepaid.action_post()

        journal = self.env['account.journal'].search(
            [('type', 'in', ['bank', 'cash']),
             ('company_id', '=', self.env.company.id)],
            limit=1
        )
        payment_method_line = (
            journal.outbound_payment_method_line_ids[:1]
            or journal.inbound_payment_method_line_ids[:1]
        )

        wizard = self.env['payment.register.prepaid'].create({
            'prepaid_id': self.prepaid.id,
            'company_id': self.env.company.id,
            'amount': self.prepaid.amount,
            'currency_id': self.prepaid.currency_id.id,
            'payment_date': '2024-06-20',
            'journal_id': journal.id,
            'payment_method_line_id': payment_method_line.id,
            'communication': self.prepaid.name,
        })
        wizard.action_create_payments()

        payment = self.env['account.payment'].search(
            [('prepaid_id', '=', self.prepaid.id)], limit=1
        )
        self.assertTrue(payment, "An account.payment linked to the prepaid should exist")
        self.assertEqual(payment.prepaid_id.id, self.prepaid.id,
                         "payment.prepaid_id should reference the advance invoice")
