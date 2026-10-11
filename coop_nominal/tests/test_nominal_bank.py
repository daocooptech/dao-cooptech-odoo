# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_nominal_export import NominalExportCase


@tagged('post_install', '-at_install')
class TestNominalBankStates(NominalExportCase):
    """Путь выплаты через банк: отказ, повтор, снятие, контроль банка (этап 3)."""

    def test_rejected_then_retry_with_new_key(self):
        hold, payout = self._queued_payout()
        self.account._export_payouts()
        payout.action_mark_rejected()
        self.assertEqual(payout.state, 'failed')
        self.assertTrue(payout.failure_reason)
        self.assertEqual(hold.state, 'payout_queued')
        self.assertEqual(self.account._reconcile().failed_payout_count, 1)

        retry = payout.action_retry()
        self.assertEqual((retry.version, retry.state, retry.amount), (2, 'queued', 9800.0))
        self.assertNotEqual(retry.idempotency_key, payout.idempotency_key)
        self.assertEqual(self.account._reconcile().failed_payout_count, 0)
        with self.assertRaises(UserError):
            payout.action_retry()  # живая попытка уже есть
        batch = self.account._export_payouts()
        self.assertEqual(batch.payout_ids, retry)
        self.assertEqual(retry.order_number, '2')

    def test_cancel_returns_money_to_beneficiary(self):
        hold, payout = self._queued_payout()
        payout.action_cancel()
        self.assertEqual(payout.state, 'cancelled')
        self.assertEqual(hold.state, 'held_seller')
        hold._queue_payout()
        again = hold.payout_ids.filtered(lambda p: p.state == 'queued')
        self.account._export_payouts()
        with self.assertRaises(UserError):
            again.action_cancel()  # уже в банке
        again.action_mark_rejected()
        again.action_cancel()  # отказ: деньги снова за продавцом
        self.assertEqual(again.state, 'failed')
        self.assertEqual(hold.state, 'held_seller')
        with self.assertRaises(UserError):
            again.action_retry()  # удержание выплаты уже не ждёт

    def test_bank_control_in_manual_mode(self):
        self.env['coop.nominal.setting'].create({
            'account_id': self.account.id, 'date_from': self.today,
            'fee_percent': 2.0, 'bank_control': True})
        hold, payout = self._queued_payout()
        self.assertEqual(payout.state, 'bank_review')
        self.account._export_payouts()
        self.assertEqual(payout.state, 'bank_review')
        hold._freeze()
        self.assertEqual(payout.state, 'bank_review', 'поручение уже в банке')
        self.assertEqual(hold.state, 'payout_queued')
        payout.action_mark_accepted()
        self.assertEqual(payout.state, 'sent')

    def test_bank_answers(self):
        _hold, payout = self._queued_payout()
        payout._apply_bank_answer({'status': 'timeout'})
        self.assertEqual(payout.state, 'unknown')
        payout._apply_bank_answer({'status': 'accepted', 'bank_ref': 'B-1'})
        self.assertEqual((payout.state, payout.bank_ref), ('sent', 'B-1'))
        with self.assertRaises(UserError):
            payout._apply_bank_answer({'status': 'executed'})
        with self.assertRaises(UserError):
            self.account._bank_adapter()._submit(payout)  # ручной режим
