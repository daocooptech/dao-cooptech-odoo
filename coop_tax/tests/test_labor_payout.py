# -*- coding: utf-8 -*-
"""Выплата за трудовое участие (решения 514, 516), расчёт бухгалтера
26.10 на 110 000 ₽ в месяц: взносы 33 000, травматизм 0,2 % — 220,
кооператив платит 143 220; НДФЛ 14 300, на руки 95 700. Нерезидент в
России — НДФЛ 30 %, на руки 77 000; иностранец за рубежом — 110 000."""
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.coop_base.tests.common import CoopCase


@tagged('post_install', '-at_install')
class TestLaborPayout(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.coop = cls._make_org('Артель пробы выплат')
        cls.coop.write({'coop_injury_insurance': True, 'coop_injury_rate': 0.2})
        cls.person = cls._make_person('Член артели пробы').partner_id

    def _pay(self, amount=110000, date='2026-03-25', **values):
        return self.env['coop.tax.labor.payout'].create(dict(
            values, cooperative_id=self.coop.id, partner_id=self.person.id,
            date=date, amount=amount))

    def test_rezident(self):
        pay = self._pay(resident=True)
        self.assertEqual((pay.insurance, pay.injury, pay.cost), (33000, 220, 143220))
        self.assertEqual((pay.ndfl_amount, pay.net_amount), (14300, 95700))

    def test_bez_travmatizma(self):
        self.coop.coop_injury_insurance = False
        pay = self._pay(resident=True)
        self.assertEqual((pay.injury, pay.cost), (0, 143000))

    def test_msp(self):
        pay = self._pay(resident=True, sme=True)
        self.assertEqual(pay.insurance, 22596)

    def test_nerezident_v_rossii(self):
        pay = self._pay(resident=False, work_place='ru', permit='patent')
        self.assertEqual((pay.ndfl_amount, pay.net_amount, pay.cost), (33000, 77000, 143220))

    def test_inostranec_za_rubezhom(self):
        pay = self._pay(resident=False, foreigner=True, work_place='abroad')
        self.assertEqual((pay.ndfl_amount, pay.insurance, pay.injury, pay.cost),
                         (0, 0, 0, 110000))

    def test_nerezident_bez_dokumenta(self):
        with self.assertRaises(ValidationError):
            self._pay(resident=False, work_place='ru')

    def test_baza_vznosov(self):
        self._pay(amount=2_900_000, date='2026-01-25', resident=True)
        pay = self._pay(amount=100_000, date='2026-02-25', resident=True)
        self.assertEqual(pay.insurance, round(79_000 * 0.30 + 21_000 * 0.151))

    def test_tarif_travmatizma(self):
        with self.assertRaises(ValidationError):
            self.coop.coop_injury_rate = 9.0
