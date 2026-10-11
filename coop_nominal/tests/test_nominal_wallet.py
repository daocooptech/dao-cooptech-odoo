# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_nominal_export import NominalExportCase
from .test_nominal_statement import _doc


@tagged('post_install', '-at_install')
class TestNominalWallet(NominalExportCase):
    """Фиатная вкладка: безопасные сделки и выписка за период (этап 4)."""

    def _wallet(self, partner):
        Wallet = self.env['coop.wallet']
        return Wallet.search([('partner_id', '=', partner.id)]) \
            or Wallet.create({'partner_id': partner.id})

    def _rows(self, partner, date_from=None):
        statement = self.env['coop.nominal.partner.statement'].create({
            'wallet_id': self._wallet(partner).id,
            'date_from': date_from or self.today, 'date_to': self.today})
        return statement, statement._rows()

    def test_numbers_follow_the_ledger(self):
        buyer, seller = self._wallet(self.buyer), self._wallet(self.seller)
        hold = self._hold()
        buyer.invalidate_recordset()
        self.assertEqual(buyer.nominal_to_pay, 10000.0)
        self.assertEqual(buyer.nominal_hold_ids, hold)
        self.assertEqual(seller.nominal_hold_ids, hold)

        self._import([_doc(1, self.day, '10000.00', 'CT-%s' % hold.id, '500100732259',
                           '40817810000000000001')], end='10000.00')
        (buyer | seller).invalidate_recordset()
        self.assertEqual(buyer.nominal_to_pay, 0.0)
        self.assertEqual(buyer.nominal_mine_before_act, 10000.0)
        self.assertEqual(seller.nominal_mine_to_receive, 0.0)

        hold._act(self.today)
        (buyer | seller).invalidate_recordset()
        self.assertEqual(buyer.nominal_mine_before_act, 0.0)
        self.assertEqual(seller.nominal_mine_to_receive, 9800.0)  # минус 2 % оператору

    def test_statement_balances_and_csv(self):
        hold, payout = self._queued_payout(end='10000.00')
        statement, (opening, rows, closing) = self._rows(self.seller)
        self.assertEqual(opening, 0.0)
        self.assertEqual([(r['kind'], r['income'], r['expense']) for r in rows], [
            ('Смена бенефициара', 10000.0, 0.0), ('Комиссия', 0.0, 200.0)])
        self.assertEqual(closing, 9800.0)
        self.assertEqual(rows[0]['code'], hold.code)
        self.assertEqual(rows[0]['other'], self.buyer.name)

        _statement, (opening, rows, closing) = self._rows(self.buyer)
        self.assertEqual([(r['income'], r['expense']) for r in rows],
                         [(10000.0, 0.0), (0.0, 10000.0)])
        self.assertEqual(closing, 0.0)

        action = statement.action_download()
        self.assertIn('download=true', action['url'])
        text = statement.file.content.decode('utf-8')
        self.assertTrue(text.startswith('﻿'))
        self.assertIn('Остаток на конец;;;9800,00', text)
        self.assertIn(hold.code, text)

    def test_period_order_checked(self):
        with self.assertRaises(UserError):
            self.env['coop.nominal.partner.statement'].create({
                'wallet_id': self._wallet(self.seller).id,
                'date_from': self.today, 'date_to': self.today - timedelta(days=1)})
