# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_nominal_export import NominalExportCase


@tagged('post_install', '-at_install')
class TestNominalDemoBank(NominalExportCase):
    """Демо-банк: сбои, повторы с тем же ключом, выписка (этап 3б)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.account.adapter = 'demo'
        cls.Order = cls.env['coop.nominal.demo.order']

    def _orders(self, payout):
        return self.Order.search([('payout_id.hold_id', '=', payout.hold_id.id)])

    def test_one_pass_pays_out(self):
        hold, payout = self._queued_payout()
        self.account.with_context(coop_demo_fault='none')._cron_bank_accounts()
        self.assertEqual(payout.state, 'executed')
        self.assertEqual(hold.state, 'paid_out')
        self.assertTrue(payout.order_number)
        self.assertTrue(payout.bank_ref.isdigit())
        self.assertFalse(self.account.discrepancy)
        self.assertEqual(self.account.ledger_balance, 200.0)  # комиссия оператора
        with self.assertRaises(UserError):
            self.account._export_payouts()  # файлом — только в ручном режиме

    def test_lost_answer_is_not_paid_twice(self):
        _hold, payout = self._queued_payout()
        payout.with_context(coop_demo_fault='lost')._submit_to_bank()
        self.assertEqual(payout.state, 'unknown')
        payout.with_context(coop_demo_fault='lost')._submit_to_bank()
        self.assertEqual(payout.state, 'sent')
        self.assertEqual(payout.submit_count, 2)
        self.assertEqual(len(self._orders(payout)), 1, 'одно поручение на ключ')

    def test_bank_down_then_resubmit_same_key(self):
        _hold, payout = self._queued_payout()
        payout.with_context(coop_demo_fault='down')._submit_to_bank()
        self.assertEqual(payout.state, 'unknown')
        self.assertFalse(self._orders(payout))
        payout.with_context(coop_demo_fault='down')._poll_bank()
        self.assertEqual(payout.state, 'sent')
        self.assertEqual(self._orders(payout).idempotency_key, payout.idempotency_key)

    def test_reject_and_retry(self):
        hold, payout = self._queued_payout()
        payout.with_context(coop_demo_fault='reject')._submit_to_bank()
        self.assertEqual(payout.state, 'failed')
        self.assertIn('закрыт', payout.failure_reason)
        retry = payout.action_retry()
        retry.with_context(coop_demo_fault='none')._submit_to_bank()
        self.assertEqual(retry.state, 'sent')
        self.assertEqual(len(self._orders(payout)), 2)
        self.account._fetch_statement()
        self.assertEqual(retry.state, 'executed')
        self.assertEqual(hold.state, 'paid_out')

    def test_bank_review_then_accepted(self):
        self.env['coop.nominal.setting'].create({
            'account_id': self.account.id, 'date_from': self.today,
            'fee_percent': 2.0, 'bank_control': True})
        _hold, payout = self._queued_payout()
        payout.with_context(coop_demo_fault='none')._submit_to_bank()
        self.assertEqual(payout.state, 'bank_review')
        self.assertEqual(payout.submit_count, 1)
        payout._poll_bank()
        self.assertEqual(payout.state, 'sent')

    def test_no_requisites_fails_alone(self):
        _hold, payout = self._queued_payout()
        payout.recipient_account = False
        payout._submit_to_bank()
        self.assertEqual(payout.state, 'failed')
        self.assertFalse(self._orders(payout))

    def test_daily_empty_statement(self):
        self.account._fetch_statement()
        self.assertEqual(self.account.statement_date, self.today)
        self.assertFalse(self.account.payouts_blocked)
        count = len(self.account.statement_ids)
        self.account._fetch_statement()
        self.assertEqual(len(self.account.statement_ids), count, 'за день — одна пустая')
