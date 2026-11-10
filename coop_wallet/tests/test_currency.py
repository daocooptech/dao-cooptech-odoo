# -*- coding: utf-8 -*-
"""Валюты кошелька: курсы ЦБ, пересчёт, счета, резидентство (задача 400)."""
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

CBR = '''<?xml version="1.0" encoding="windows-1251"?>
<ValCurs Date="10.11.2026" name="Foreign Currency Market">
 <Valute ID="R01235"><NumCode>840</NumCode><CharCode>USD</CharCode><Nominal>1</Nominal>
  <Name>US</Name><Value>80,5000</Value></Valute>
 <Valute ID="R01335"><NumCode>398</NumCode><CharCode>KZT</CharCode><Nominal>100</Nominal>
  <Name>KZT</Name><Value>16,0000</Value></Valute>
</ValCurs>'''.encode('windows-1251')


@tagged('post_install', '-at_install')
class TestCurrency(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Rate = self.env['coop.currency.rate']
        self.rub = self.env.ref('base.RUB')
        self.usd = self.env.ref('base.USD')
        self.kzt = self.env.ref('base.KZT')

    def test_currency_set(self):
        enabled = self.env['res.currency'].with_context(active_test=False).search(
            [('coop_wallet_enabled', '=', True)])
        names = set(enabled.mapped('name'))
        self.assertTrue({'RUB', 'CNY', 'KZT', 'EUR', 'USD', 'VND', 'CUP'} <= names)
        # Не включены: SAR и MDL — до отдельного слова владельца (решение 640).
        self.assertFalse({'SAR', 'MDL'} & names)
        self.assertEqual(self.rub.symbol, '₽')

    def test_parse_cbr_divides_by_nominal(self):
        day, rates = self.Rate._parse_cbr(CBR)
        self.assertEqual(day, date(2026, 11, 10))
        self.assertAlmostEqual(rates['USD'], 80.5)
        self.assertAlmostEqual(rates['KZT'], 0.16)

    def test_store_and_convert_via_ruble(self):
        day, rates = self.Rate._parse_cbr(CBR)
        self.assertEqual(self.Rate.coop_store_rates(day, rates), 2)
        # Повтор на ту же дату обновляет, а не дублирует.
        self.assertEqual(self.Rate.coop_store_rates(day, rates), 2)
        self.assertEqual(self.Rate.search_count(
            [('currency_id', '=', self.usd.id), ('date', '=', day)]), 1)
        # 1 000 тенге → доллары через рубль: 1000 × 0,16 / 80,5.
        got = self.Rate.coop_convert(1000, self.kzt, self.usd, day)
        self.assertAlmostEqual(got, 1000 * 0.16 / 80.5)
        self.assertEqual(self.Rate.coop_convert(5, self.usd, self.usd, day), 5)

    def test_missing_rate_is_none_not_zero(self):
        cny = self.env.ref('base.CNY')
        self.Rate.search([('currency_id', '=', cny.id)]).unlink()
        self.assertIsNone(
            self.Rate.coop_convert(100, cny, self.rub, date(2026, 11, 10)))

    def test_stale_rate_flagged(self):
        self.Rate.search([('currency_id', '=', self.usd.id)]).unlink()
        self.Rate.create({'currency_id': self.usd.id, 'date': date(2026, 11, 1),
                          'rub_per_unit': 80})
        rate, rate_day, stale = self.Rate.coop_rate(self.usd, date(2026, 11, 10))
        self.assertEqual(rate_day, date(2026, 11, 1))
        self.assertTrue(stale)

    def _wallet(self, **vals):
        partner = self.env['res.partner'].create(dict({'name': 'Тест кошелька'}, **vals))
        return self.env['coop.wallet'].wallet_for(partner)

    def test_balances_per_currency_and_summary(self):
        wallet = self._wallet()
        Move = self.env['coop.wallet.movement']
        Move.create({'wallet_id': wallet.id, 'name': 'Руб', 'amount': 1000,
                     'kind': 'correction'})
        Move.create({'wallet_id': wallet.id, 'name': 'Тенге', 'amount': 5000,
                     'kind': 'correction', 'currency_id': self.kzt.id})
        rows = {r['currency'].name: r for r in wallet.coop_balances()}
        self.assertEqual(rows['RUB']['balance'], 1000)
        self.assertEqual(rows['KZT']['balance'], 5000)
        # fiat_balance — только валюта кошелька.
        self.assertEqual(wallet.fiat_balance, 1000)
        day = date(2026, 11, 10)
        self.Rate.search([('currency_id', '=', self.kzt.id)]).unlink()
        res = wallet.coop_summary(self.rub, day)
        self.assertEqual(res['total'], 1000)
        self.assertEqual(res['missing'], [self.kzt])
        self.Rate.create({'currency_id': self.kzt.id, 'date': day,
                          'rub_per_unit': 0.16})
        res = wallet.coop_summary(self.rub, day)
        self.assertAlmostEqual(res['total'], 1000 + 5000 * 0.16)
        self.assertFalse(res['missing'])

    def test_one_main_account_per_currency(self):
        wallet = self._wallet()
        Account = self.env['coop.wallet.account']
        Account.create({'wallet_id': wallet.id, 'currency_id': self.kzt.id,
                        'label': 'Kaspi', 'is_main': True})
        with self.assertRaises(ValidationError):
            Account.create({'wallet_id': wallet.id, 'currency_id': self.kzt.id,
                            'label': 'Halyk', 'is_main': True})
        Account.create({'wallet_id': wallet.id, 'currency_id': self.usd.id,
                        'label': 'USD', 'is_main': True})

    def test_cbdc_only_for_confirmed_currencies(self):
        wallet = self._wallet()
        Account = self.env['coop.wallet.account']
        Account.create({'wallet_id': wallet.id, 'currency_id': self.rub.id,
                        'kind': 'cbdc', 'label': 'Цифровой рубль'})
        with self.assertRaises(ValidationError):
            Account.create({'wallet_id': wallet.id, 'currency_id': self.usd.id,
                            'kind': 'cbdc', 'label': 'Цифровой доллар'})

    def test_summary_currency_and_residency(self):
        kz, ru = self.env.ref('base.kz'), self.env.ref('base.ru')
        both = self.env['res.partner'].create({
            'name': 'Двойное',
            'coop_citizenship_ids': [(6, 0, [ru.id, kz.id])]})
        self.assertEqual(both.coop_summary_currency(), self.rub)
        both.coop_summary_country_id = kz
        self.assertEqual(both.coop_summary_currency(), self.kzt)
        nobody = self.env['res.partner'].create({'name': 'Без гражданства'})
        self.assertEqual(nobody.coop_summary_currency(), self.rub)
        self.assertTrue(both.coop_ru_resident)
        foreign = self.env['res.partner'].create({
            'name': 'Иностранец', 'coop_citizenship_ids': [(6, 0, [kz.id])]})
        self.assertFalse(foreign.coop_ru_resident)
        foreign.coop_ru_residence_permit = True
        self.assertTrue(foreign.coop_ru_resident)

    def test_currency_warning_only_between_ru_residents(self):
        ru = self.env.ref('base.ru')
        Partner = self.env['res.partner']
        a = Partner.create({'name': 'А', 'coop_citizenship_ids': [(6, 0, [ru.id])]})
        b = Partner.create({'name': 'Б', 'coop_citizenship_ids': [(6, 0, [ru.id])]})
        c = Partner.create({'name': 'В'})
        self.assertTrue(a.coop_currency_warning(b, self.usd))
        self.assertFalse(a.coop_currency_warning(b, self.rub))
        self.assertFalse(a.coop_currency_warning(c, self.usd))
        self.assertTrue(a.coop_foreign_account_hint(self.env.ref('base.kz')))
        self.assertFalse(a.coop_foreign_account_hint(ru))
