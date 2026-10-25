# -*- coding: utf-8 -*-
"""Валюта участника — решение 482.

Гражданам и организациям России — рубли без выбора, остальным — своя.
Проверяется правило, а не вид экрана: ошибиться здесь значит выставить
россиянину цены в юанях или иностранцу — в рублях без его ведома.
"""
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.coop_base.tests.common import CoopCase


@tagged('post_install', '-at_install')
class TestCurrency(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rub = cls.env.ref('base.RUB')
        cls.cny = cls.env.ref('base.CNY')
        cls.cny.active = True
        cls.russian = cls._make_person('Резидентный Участник')
        cls.foreigner = cls._make_person('Иностранный Участник')
        cls.foreigner.partner_id.write({
            'coop_fx_resident': False,
            'country_id': cls.env.ref('base.cn').id,
        })

    def test_rossiyaninu_rubli_bez_vybora(self):
        partner = self.russian.partner_id
        self.assertTrue(self.russian.coop_currency_rub_only)
        self.assertEqual(partner._coop_currency(), self.rub)
        with self.assertRaises(UserError):
            partner.coop_currency_id = self.cny

    def test_grazhdanin_za_granitsey_tozhe_v_rublyah(self):
        """Валютный резидент — по гражданству, а не по месту жительства."""
        partner = self.russian.partner_id
        partner.country_id = self.env.ref('base.am')
        self.assertEqual(partner._coop_currency(), self.rub)

    def test_inostranets_vybiraet(self):
        partner = self.foreigner.partner_id
        self.assertFalse(self.foreigner.coop_currency_rub_only)
        self.assertEqual(partner._coop_currency(), self.rub,
                         'до выбора — рубли платформы')
        self.foreigner.coop_currency_id = self.cny
        self.assertEqual(partner._coop_currency(), self.cny)
