# -*- coding: utf-8 -*-
"""Сеть не отвечает: плашка и выключенные переводы (решение 658 п. 1)."""
from datetime import datetime
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestNetworkDown(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ton = self.env.ref('coop_wallet.network_ton')
        self.ton.write({'is_down': False, 'reached_at': False})
        partner = self.env['res.partner'].create({'name': 'Сеть-тест'})
        self.wallet = self.env['coop.wallet'].wallet_for(partner)
        self.asset = self.env['coop.wallet.asset'].create({
            'wallet_id': self.wallet.id, 'network_id': self.ton.id,
            'name': 'Toncoin', 'symbol': 'TON', 'quantity': 10.0,
            'valuation': 3000.0})
        self.Network = self.env['coop.wallet.network']

    def _send(self):
        return self.env['coop.wallet.operation'].create({
            'wallet_id': self.wallet.id, 'mode': 'send',
            'asset_id': self.asset.id, 'quantity': 1.0,
            'peer_address': 'UQ-test'})

    def test_cron_marks_down_and_keeps_last_answer(self):
        with patch.object(type(self.Network), '_coop_probe', return_value=True):
            self.Network._cron_check_reachability()
        self.assertFalse(self.ton.is_down)
        reached = self.ton.reached_at
        self.assertTrue(reached)
        with patch.object(type(self.Network), '_coop_probe', return_value=False):
            self.Network._cron_check_reachability()
        self.assertTrue(self.ton.is_down)
        self.assertEqual(self.ton.reached_at, reached,
                         'время последнего ответа не сдвигается сбоем')

    def test_note_has_time_of_last_answer(self):
        self.assertEqual(self.ton._coop_down_note(), '')
        self.ton.write({'is_down': True, 'reached_at': datetime(2026, 11, 13, 11, 5)})
        note = self.ton.with_context(tz='Europe/Moscow')._coop_down_note()
        self.assertIn('Сеть TON недоступна, данные на', note)
        self.assertIn('14:05', note)

    def test_send_blocked_while_down(self):
        self.ton.write({'is_down': True, 'reached_at': datetime(2026, 11, 13, 11, 5)})
        wizard = self._send()
        self.assertTrue(wizard.network_down_note)
        with self.assertRaises(UserError):
            wizard.action_confirm()
        self.assertEqual(self.asset.quantity, 10.0)
        self.assertIn('Переводы в эту сеть выключены', self.wallet.networks_down_note)

    def test_send_works_when_up(self):
        wizard = self._send()
        self.assertFalse(wizard.network_down_note)
        self.assertFalse(self.wallet.networks_down_note)
        wizard.action_confirm()
        self.assertEqual(self.asset.quantity, 9.0)

    def test_check_up_stops_exchange_orders(self):
        self.Network._coop_check_up('ton', 'Заявки биржи')
        self.ton.is_down = True
        with self.assertRaisesRegex(UserError, 'Заявки биржи выключены'):
            self.Network._coop_check_up('ton', 'Заявки биржи')
