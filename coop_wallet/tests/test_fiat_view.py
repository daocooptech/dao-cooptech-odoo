# -*- coding: utf-8 -*-
"""Вкладка «Фиат»: переключатель, показатели, счета, пополнение цифровым рублём (задача 400)."""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFiatView(TransactionCase):

    def setUp(self):
        super().setUp()
        self.rub = self.env.ref('base.RUB')
        self.cny = self.env.ref('base.CNY')
        self.myr = self.env.ref('base.MYR')
        Rate = self.env['coop.currency.rate']
        Rate.search([]).unlink()
        Rate.create({'currency_id': self.cny.id, 'date': date.today(),
                     'rub_per_unit': 10.0})
        partner = self.env['res.partner'].create({'name': 'Фиат-тест'})
        self.wallet = self.env['coop.wallet'].wallet_for(partner)
        Account = self.env['coop.wallet.account']
        self.rub_acc = Account.create({
            'wallet_id': self.wallet.id, 'currency_id': self.rub.id,
            'label': 'Счёт RUB', 'is_main': True})
        self.cny_acc = Account.create({
            'wallet_id': self.wallet.id, 'currency_id': self.cny.id,
            'label': 'Счёт CNY', 'is_main': True})
        Move = self.env['coop.wallet.movement']
        Move.create({'wallet_id': self.wallet.id, 'account_id': self.rub_acc.id,
                     'name': 'Руб', 'amount': 1000, 'kind': 'correction'})
        Move.create({'wallet_id': self.wallet.id, 'account_id': self.cny_acc.id,
                     'currency_id': self.cny.id, 'name': 'Юань', 'amount': 200,
                     'kind': 'correction'})

    def test_all_sums_in_summary_currency(self):
        self.wallet.fiat_currency = 'all'
        # 1 000 ₽ + 200 CNY × 10 = 3 000 ₽
        self.assertIn('3 000,00', self.wallet.fiat_stat_total)
        self.assertTrue(self.wallet.fiat_stat_total.startswith('≈'))
        self.assertEqual(self.wallet.fiat_stat_count, 2)
        self.assertEqual(len(self.wallet.fiat_account_ids), 2)
        self.assertTrue(self.wallet.fiat_by_currency)

    def test_single_currency_filters_everything(self):
        self.wallet.fiat_currency = 'CNY'
        self.assertEqual(self.wallet.fiat_stat_total, '200,00 CNY')
        self.assertEqual(self.wallet.fiat_account_ids, self.cny_acc)
        self.assertEqual(len(self.wallet.fiat_movement_ids), 1)
        self.assertFalse(self.wallet.fiat_by_currency)
        self.assertFalse(self.wallet.fiat_can_pay)

    def test_missing_rate_hides_total(self):
        self.env['coop.wallet.account'].create({
            'wallet_id': self.wallet.id, 'currency_id': self.myr.id,
            'label': 'Счёт MYR', 'is_main': True})
        self.env['coop.wallet.movement'].create({
            'wallet_id': self.wallet.id, 'currency_id': self.myr.id,
            'name': 'Ринггит', 'amount': 50, 'kind': 'correction'})
        self.wallet.fiat_currency = 'all'
        self.assertEqual(self.wallet.fiat_stat_total, '—')
        self.assertIn('MYR', self.wallet.fiat_rates_note)

    def test_empty_balance_without_rate_is_not_missing(self):
        self.env['coop.wallet.account'].create({
            'wallet_id': self.wallet.id, 'currency_id': self.myr.id,
            'label': 'Пустой MYR', 'is_main': True})
        self.wallet.fiat_currency = 'all'
        self.assertTrue(self.wallet.fiat_stat_total.startswith('≈'))

    def test_pay_buttons_only_for_digital_ruble(self):
        self.wallet.fiat_currency = 'RUB'
        self.assertFalse(self.wallet.fiat_can_pay)
        self.assertIn('цифровой рубль', self.wallet.fiat_pay_hint)
        self.env['coop.wallet.account'].create({
            'wallet_id': self.wallet.id, 'currency_id': self.rub.id,
            'kind': 'cbdc', 'label': 'Цифровой рубль'})
        self.wallet.invalidate_recordset()
        self.wallet.fiat_currency = 'RUB'
        self.assertTrue(self.wallet.fiat_can_pay)
        self.wallet.fiat_currency = 'all'
        self.assertFalse(self.wallet.fiat_can_pay)

    def test_topup_goes_through_digital_ruble_account(self):
        cbdc = self.env['coop.wallet.account'].create({
            'wallet_id': self.wallet.id, 'currency_id': self.rub.id,
            'kind': 'cbdc', 'label': 'Цифровой рубль'})
        wizard = self.env['coop.wallet.operation'].create({
            'wallet_id': self.wallet.id, 'mode': 'topup', 'amount': 500,
            'account_id': cbdc.id})
        wizard.action_confirm()
        move = self.wallet.movement_ids.filtered(lambda m: m.kind == 'topup')
        self.assertEqual(move.account_id, cbdc)
        self.assertEqual(move.amount, 500)
        no_account = self.env['coop.wallet.operation'].create({
            'wallet_id': self.wallet.id, 'mode': 'topup', 'amount': 5})
        with self.assertRaises(UserError):
            no_account.action_confirm()
