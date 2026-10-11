# -*- coding: utf-8 -*-
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestNominalDeal(TransactionCase):
    """Безопасная сделка: удержания идут за сделкой (этап 1б)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.context_today(cls.env['coop.nominal.hold'])
        cls.seller = cls._user('Продавец безопасной сделки')
        cls.buyer = cls._user('Покупатель безопасной сделки')
        cls.account = cls.env['coop.nominal.account'].create({
            'name': 'Номинальный счёт сделок',
            'owner_id': cls.env['res.partner'].create(
                {'name': 'ООО «Оператор сделок»', 'is_company': True}).id,
            'currency_id': cls.env.company.currency_id.id,
            'setting_ids': [(0, 0, {
                'date_from': cls.today - timedelta(days=30),
                'fee_percent': 1.0,
            })],
        })

    @classmethod
    def _user(cls, name):
        return cls.env['res.users'].create({
            'name': name, 'login': name.replace(' ', '-').lower(),
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    def _deal(self, channel='nominal'):
        deal = self.env['coop.deal'].create({
            'name': 'Поставка зерна',
            'party_a_id': self.seller.partner_id.id,
            'party_b_id': self.buyer.partner_id.id,
            'payment_channel': channel,
            'payment_ids': [(0, 0, {
                'due_on': self.today,
                'amount': 50000.0,
                'payer_id': self.buyer.partner_id.id,
                'payee_id': self.seller.partner_id.id,
            })],
        })
        with patch.object(type(self.env['res.partner']), 'coop_require_level',
                          return_value=True):
            deal.with_user(self.seller).action_agree()
        return deal

    def _credit(self, deal):
        hold = deal.nominal_hold_ids
        hold._credit(self.today)
        self.account.write({'statement_balance': self.account.ledger_balance,
                            'statement_date': self.today})
        return hold

    def test_direct_deal_has_no_holds(self):
        deal = self._deal('direct')
        self.assertFalse(deal.nominal_hold_ids)
        self.assertEqual(deal.payment_ids.channel, 'direct')

    def test_agree_creates_hold_with_code(self):
        deal = self._deal()
        hold = deal.nominal_hold_ids
        self.assertEqual(len(hold), 1)
        self.assertEqual(hold.state, 'awaiting')
        self.assertEqual(deal.payment_ids.nominal_code, hold.code)
        with self.assertRaises(UserError):
            deal.payment_ids.with_user(self.seller).action_mark_paid()
        with self.assertRaises(UserError):
            deal.payment_ids.write({'channel': 'direct'})

    def test_act_moves_money_to_seller_and_queues_payout(self):
        deal = self._deal()
        hold = self._credit(deal)
        self.assertEqual(deal.payment_ids.state, 'paid')
        deal.with_user(self.buyer).action_confirm_act()
        self.assertEqual(hold.state, 'held_buyer')
        deal.with_user(self.seller).action_confirm_act()
        self.assertEqual(deal.state, 'done')
        self.assertEqual(hold.state, 'payout_queued')
        self.assertEqual(hold.payout_ids.amount, 49500.0)

    def test_dispute_freezes_and_resolution_unfreezes(self):
        deal = self._deal()
        hold = self._credit(deal)
        deal.with_user(self.buyer).action_open_dispute()
        self.assertEqual(hold.state, 'frozen')
        deal.dispute_resolution = 'Поставка состоялась частично.'
        deal.with_user(self.env.ref('base.user_admin')).action_resolve_dispute()
        self.assertEqual(hold.state, 'held_buyer')

    def test_cancel_refunds_or_cancels(self):
        unpaid = self._deal()
        unpaid.with_user(self.buyer).action_cancel()
        self.assertEqual(unpaid.nominal_hold_ids.state, 'cancelled')
        paid = self._deal()
        hold = self._credit(paid)
        paid.with_user(self.buyer).action_cancel()
        self.assertEqual(hold.state, 'refund_queued')
        self.assertEqual(hold.payout_ids.partner_id, self.buyer.partner_id)
