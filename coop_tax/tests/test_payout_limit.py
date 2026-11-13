# -*- coding: utf-8 -*-
"""Лимит кооперативных выплат (решение 517), пример бухгалтера 26.10:
доходы 10 000 000, расходы 8 000 000, УСН 600 000, чистая прибыль
1 400 000 — потолок 280 000 от прибыли и 1 400 000 от доходов после
обязательных платежей (20 % от 9 400 000 упирается в прибыль)."""
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.coop_base.tests.common import CoopCase


@tagged('post_install', '-at_install')
class TestPayoutLimit(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.coop = cls._make_org('Кооператив пробы лимита')
        person = cls._make_person('Пайщик пробы лимита').partner_id
        wallet = cls.env['coop.wallet'].search([('partner_id', '=', person.id)], limit=1) \
            or cls.env['coop.wallet'].create({'partner_id': person.id})
        cls.account = cls.env['coop.share.account'].create(
            {'wallet_id': wallet.id, 'cooperative_id': cls.coop.id})

    def _limit(self, base_kind):
        self.coop.coop_payout_limit_base = base_kind
        return self.env['coop.tax.payout.limit'].create({
            'cooperative_id': self.coop.id, 'year': 2025,
            'net_profit': 1_400_000, 'income_after_taxes': 9_400_000,
            'retained': 1_400_000})

    def _accrual(self, amount, date='2026-03-01'):
        return self.env['coop.share.move'].create({
            'account_id': self.account.id, 'date': date, 'name': 'По итогам года',
            'kind': 'accrual', 'amount': amount, 'basis': 'Протокол № 2'})

    def test_ot_pribyli(self):
        limit = self._limit('net_profit')
        self.assertEqual((limit.base, limit.limit), (1_400_000, 280_000))

    def test_ot_dohodov_upiraetsya_v_pribyl(self):
        limit = self._limit('income_after_taxes')
        self.assertEqual((limit.base, limit.limit), (9_400_000, 1_400_000))

    def test_sverh_limita_ne_provoditsya(self):
        limit = self._limit('net_profit')
        move = self._accrual(200_000)
        self.assertEqual(move.coop_result_year, 2025)
        self.assertFalse(move.coop_limit_missing)
        self.assertEqual(limit.remaining, 80_000)
        with self.assertRaises(ValidationError):
            self._accrual(100_000)
        self._accrual(80_000)

    def test_bez_limita_preduprezhdenie(self):
        move = self._accrual(50_000, date='2027-02-01')
        self.assertEqual(move.coop_result_year, 2026)
        self.assertTrue(move.coop_limit_missing)

    def test_zayavlennoe_ne_schitaetsya(self):
        limit = self._limit('net_profit')
        self.env['coop.share.move'].create({
            'account_id': self.account.id, 'date': '2026-03-01', 'name': 'Заявка',
            'kind': 'accrual', 'amount': 500_000, 'basis': 'Протокол № 3',
            'state': 'requested'})
        self.assertEqual(limit.accrued, 0)

    def test_delitel(self):
        """Решение 659 п. 2: делитель — сумма и базы, на единицу базы."""
        self.env['coop.share.move'].create({
            'account_id': self.account.id, 'date': '2025-02-01', 'name': 'Pai',
            'kind': 'share', 'amount': 100_000, 'basis': 'Protokol 1'})
        limit = self._limit('net_profit')
        limit.write({'distribute_total': 200_000, 'pct_labor': 50,
                     'pct_turnover': 30, 'pct_share': 20,
                     'base_labor_hours': 1000, 'base_turnover': 600_000})
        self.assertEqual((limit.base_shares, limit.member_count), (100_000, 1))
        self.assertAlmostEqual(limit.per_hour, 100)
        self.assertAlmostEqual(limit.per_turnover_rub, 0.1)
        self.assertAlmostEqual(limit.per_share_rub, 0.4)
        with self.assertRaises(ValidationError):
            limit.write({'pct_share': 30})          # 110 %
        with self.assertRaises(ValidationError):
            limit.write({'distribute_total': 300_000})  # больше лимита 280 000

    def test_artel_po_payam_ne_bolshe_poloviny(self):
        self.coop.coop_legal_form_id = self.env['coop.legal.form'].search(
            [('code', '=', 'artel')], limit=1)
        self.assertEqual(self.coop.coop_cooperative_kind, 'production')
        limit = self._limit('net_profit')
        with self.assertRaises(ValidationError):
            limit.write({'distribute_total': 100_000, 'pct_labor': 40, 'pct_share': 60})
        limit.write({'distribute_total': 100_000, 'pct_labor': 50, 'pct_share': 50})
