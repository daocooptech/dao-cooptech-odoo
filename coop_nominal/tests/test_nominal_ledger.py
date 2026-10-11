# -*- coding: utf-8 -*-
from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestNominalLedger(TransactionCase):
    """Номинальный счёт: книга, доли, инварианты (этап 1)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.context_today(cls.env['coop.nominal.share'])
        Partner = cls.env['res.partner']
        cls.operator = Partner.create({'name': 'ООО «Оператор пробы»', 'is_company': True})
        cls.buyer = Partner.create({'name': 'Покупатель пробы'})
        cls.seller = Partner.create({'name': 'Продавец пробы'})
        cls.account = cls.env['coop.nominal.account'].create({
            'name': 'Номинальный счёт пробы',
            'owner_id': cls.operator.id,
            'setting_ids': [(0, 0, {
                'date_from': cls.today - timedelta(days=30),
                'fee_percent': 2.0,
                'fee_vat_percent': 20.0,
            })],
        })
        cls.deal = cls.env['coop.deal'].create({
            'name': 'Поставка мёда',
            'party_a_id': cls.seller.id,
            'party_b_id': cls.buyer.id,
        })

    def _share(self, amount=10000.0):
        payment = self.env['coop.deal.payment'].create({
            'deal_id': self.deal.id,
            'due_on': self.today,
            'amount': amount,
            'payer_id': self.buyer.id,
            'payee_id': self.seller.id,
        })
        return self.env['coop.nominal.share'].create({
            'account_id': self.account.id,
            'payment_id': payment.id,
            'payer_id': self.buyer.id,
            'payee_id': self.seller.id,
            'amount': amount,
        })

    def _statement_matches_ledger(self):
        self.account.write({
            'statement_balance': self.account.ledger_balance,
            'statement_date': self.today,
        })

    def test_entries_are_immutable(self):
        Entry = self.env['coop.nominal.entry']
        with self.assertRaises(UserError):
            Entry.create({'account_id': self.account.id, 'event_key': 'x',
                          'kind': 'credit', 'leg': 'bank', 'amount': 1.0,
                          'date': self.today})
        share = self._share()
        share._credit(self.today)
        with self.assertRaises(UserError):
            share.entry_ids[0].write({'amount': 1.0})
        with self.assertRaises(UserError):
            share.entry_ids.unlink()

    def test_event_must_balance(self):
        Entry = self.env['coop.nominal.entry']
        with self.assertRaises(UserError):
            Entry._post(self.account, 'credit', self.today, [
                {'leg': 'bank', 'amount': 100.0},
                {'leg': 'holder', 'amount': -90.0, 'partner': self.buyer},
            ])
        with self.assertRaises(UserError):
            Entry._post(self.account, 'credit', self.today, [
                {'leg': 'bank', 'amount': 100.0},
                {'leg': 'holder', 'amount': -100.0},
            ])

    def test_full_path_both_beneficiaries(self):
        share = self._share()
        self.assertEqual(share.code, 'CT-%s' % share.id)
        self.assertEqual(share.fee_amount, 200.0)
        self.assertEqual(share.vat_amount, 33.33)
        share._credit(self.today)
        self.assertEqual(share.state, 'held_buyer')
        self.assertEqual(share.beneficiary_id, self.buyer)
        self.assertEqual(share.payment_id.state, 'paid')
        self.assertEqual(self.account.ledger_balance, 10000.0)

        share._act(self.today)
        self.assertEqual(share.state, 'held_seller')
        self.assertEqual(share.beneficiary_id, self.seller)
        self.assertEqual(share.held_amount, 9800.0)

        self._statement_matches_ledger()
        share._queue_payout()
        payout = share.payout_ids
        self.assertEqual((payout.amount, payout.state), (9800.0, 'queued'))
        self.assertEqual(len(payout.idempotency_key), 64)

        payout._mark_executed(self.today)
        self.assertEqual(share.state, 'paid_out')
        self.assertEqual(share.paid_out_on, self.today)
        self.assertEqual(share.held_amount, 0.0)
        # На счёте осталась только комиссия оператора.
        self.assertEqual(self.account.ledger_balance, 200.0)
        for key in set(self.account.share_ids.entry_ids.mapped('event_key')):
            entries = self.env['coop.nominal.entry'].search([('event_key', '=', key)])
            self.assertAlmostEqual(sum(entries.mapped('amount')), 0.0)

    def test_discrepancy_blocks_payouts(self):
        share = self._share()
        share._credit(self.today)
        share._act(self.today)
        with self.assertRaises(UserError):
            share._queue_payout()  # выписки ещё нет
        self.account.write({'statement_balance': 5000.0, 'statement_date': self.today})
        self.assertTrue(self.account.payouts_blocked)
        self.assertEqual(self.account.discrepancy, -5000.0)
        with self.assertRaises(UserError):
            share._queue_payout()
        self._statement_matches_ledger()
        self.assertFalse(self.account.payouts_blocked)
        share._queue_payout()

    def test_payout_within_share_and_one_live(self):
        share = self._share()
        share._credit(self.today)
        share._act(self.today)
        self._statement_matches_ledger()
        Payout = self.env['coop.nominal.payout']
        with self.assertRaises(ValidationError):
            Payout.create({'share_id': share.id, 'kind': 'payout',
                           'partner_id': self.seller.id, 'amount': 9800.01})
        share._queue_payout()
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError), self.env.cr.savepoint():
            Payout.create({'share_id': share.id, 'kind': 'payout',
                           'partner_id': self.seller.id, 'amount': 1.0})

    def test_refund_before_act(self):
        share = self._share(5000.0)
        share._credit(self.today)
        self._statement_matches_ledger()
        share._queue_refund()
        self.assertEqual(share.state, 'refund_queued')
        share.payout_ids._mark_executed(self.today)
        self.assertEqual(share.state, 'refunded')
        self.assertEqual(self.account.ledger_balance, 0.0)

    def test_refund_after_act_refused(self):
        share = self._share()
        share._credit(self.today)
        share._act(self.today)
        self._statement_matches_ledger()
        with self.assertRaises(UserError):
            share._queue_refund()

    def test_seller_mode_refund_needs_consent(self):
        self.env['coop.nominal.setting'].create({
            'account_id': self.account.id,
            'date_from': self.today,
            'beneficiary_mode': 'seller',
        })
        share = self._share(3000.0)
        self.assertEqual(share.beneficiary_mode, 'seller')
        share._credit(self.today)
        self.assertEqual(share.state, 'held_seller')
        self.assertEqual(share.beneficiary_id, self.seller)
        self._statement_matches_ledger()
        with self.assertRaises(UserError):
            share._queue_refund()
        user = self.env['res.users'].create({
            'name': 'Продавец пробы', 'login': 'nominal-seller',
            'partner_id': self.seller.id,
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        stranger = self.env['res.users'].create({
            'name': 'Посторонний', 'login': 'nominal-stranger',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        with self.assertRaises(UserError):
            share.with_user(stranger).action_consent_refund()
        share.with_user(user).action_consent_refund()
        share._queue_refund()
        self.assertEqual(share.payout_ids.partner_id, self.buyer)

    def test_freeze_and_unfreeze(self):
        share = self._share()
        share._credit(self.today)
        share._act(self.today)
        self._statement_matches_ledger()
        share._queue_payout()
        share._freeze()
        self.assertEqual(share.state, 'frozen')
        self.assertEqual(share.payout_ids.state, 'cancelled')
        with self.assertRaises(UserError):
            share._queue_payout()
        share._unfreeze()
        self.assertEqual(share.state, 'held_seller')
        share._queue_payout()
        self.assertEqual(share.payout_ids.mapped('version'), [2, 1])

    def test_cancel_before_payment(self):
        share = self._share()
        share._cancel()
        self.assertEqual(share.state, 'cancelled')
        with self.assertRaises(UserError):
            share._credit(self.today)

    def test_share_terms_and_settings_frozen(self):
        share = self._share()
        with self.assertRaises(UserError):
            share.write({'amount': 1.0})
        started = self.account.setting_ids
        with self.assertRaises(UserError):
            started.write({'fee_percent': 5.0})
        with self.assertRaises(UserError):
            started.unlink()
        with self.assertRaises(UserError):
            self.env['coop.nominal.setting'].create({
                'account_id': self.account.id,
                'date_from': self.today - timedelta(days=1),
            })
        future = self.env['coop.nominal.setting'].create({
            'account_id': self.account.id,
            'date_from': self.today + timedelta(days=10),
            'fee_percent': 5.0,
        })
        future.write({'fee_percent': 4.0})
        self.assertEqual(share.fee_amount, 200.0)
