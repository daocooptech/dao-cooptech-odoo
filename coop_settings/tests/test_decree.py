# -*- coding: utf-8 -*-
"""Страны перечня 430-р — закрываются только сделки по указам (решение 500).

Общего значка «Сделки временно недоступны» больше нет: с 01.10.2026
платформа не вправе ограничивать доступ сверх закона (ч. 2 ст. 3 289-ФЗ).
Закрыты займы и недвижимость (указы № 81 и № 95) — и только по
гражданству и регистрации стороны, а не по стране проживания.
"""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.coop_base.tests.common import CoopCase


@tagged('post_install', '-at_install')
class TestDecree(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref('base.de').coop_unfriendly = True
        cls.russian = cls._make_person('Резидент Займодавец')
        cls.russian.partner_id.write({
            'coop_fx_resident': True, 'coop_citizenship_id': cls.env.ref('base.ru').id,
            'country_id': cls.env.ref('base.ru').id})
        cls.german = cls._make_person('Гражданин Германии').partner_id
        cls.german.write({
            'coop_fx_resident': False, 'coop_citizenship_id': cls.env.ref('base.de').id,
            'country_id': cls.env.ref('base.de').id})
        # Гражданин РФ, живущий в Берлине, — ограничений нет.
        cls.berliner = cls._make_person('Россиянин в Берлине').partner_id
        cls.berliner.write({
            'coop_fx_resident': True, 'coop_citizenship_id': cls.env.ref('base.ru').id,
            'country_id': cls.env.ref('base.de').id})

    def _deal(self, borrower, lender, way='credit', amount=100000.0, **extra):
        values = {
            'name': 'Проба указов', 'way': way, 'amount': amount,
            'party_a_id': borrower.id, 'party_b_id': lender.id,
            'role_a': 'заёмщик' if way == 'credit' else 'покупатель',
            'role_b': 'кредитор' if way == 'credit' else 'продавец',
        }
        values.update(extra)
        return self.env['coop.deal'].create(values)

    def test_zaem_inostrantsu_zakryt_ukazom_81(self):
        deal = self._deal(self.german, self.russian.partner_id)
        self.assertIn('№ 81', deal._coop_decree_block())
        self.assertIn('не проводит', deal.coop_settlement_html)
        deal.line_ids = [(0, 0, {'name': 'Заём', 'quantity': 1.0, 'price_unit': 100000.0})]
        level = patch.object(type(self.env['res.partner']), 'coop_require_level',
                             return_value=True)
        with level, self.assertRaisesRegex(UserError, '№ 81'):
            deal.with_user(self.russian).action_agree()

    def test_grazhdanin_rf_za_granitsey_bez_ogranicheniy(self):
        deal = self._deal(self.berliner, self.russian.partner_id)
        self.assertFalse(deal._coop_decree_block())

    def test_vozvrat_zayma_do_10_mln_mozhno_svyshe_cherez_schet_s(self):
        small = self._deal(self.russian.partner_id, self.german, amount=5_000_000.0)
        self.assertFalse(small._coop_decree_block())
        big = self._deal(self.russian.partner_id, self.german, amount=20_000_000.0)
        self.assertIn('№ 95', big._coop_decree_block())

    def test_prochie_sdelki_kak_obychno(self):
        deal = self._deal(self.german, self.russian.partner_id, way='service')
        self.assertFalse(deal._coop_decree_block())
        self.assertNotIn('не проводит', deal.coop_settlement_html)
        self.assertIn('430-р', deal.coop_settlement_html)

    def test_nedvizhimost_tolko_arenda(self):
        Category = self.env['coop.resource.category']
        root = Category.search([('name', '=', 'Недвижимость'), ('parent_id', '=', False)], limit=1) \
            or Category.create({'name': 'Недвижимость'})
        house = Category.create({'name': 'Дома пробы', 'parent_id': root.id})
        listing = self.env['coop.resource'].create({
            'name': 'Дом в Подмосковье', 'listing_type': 'offer',
            'owner_id': self.russian.partner_id.id, 'price': 9_000_000,
            'category_id': house.id})
        sale = self._deal(self.german, self.russian.partner_id, way='sale',
                          resource_id=listing.id)
        self.assertIn('недвижимость', sale._coop_decree_block())
        rent = self._deal(self.german, self.russian.partner_id, way='rent',
                          resource_id=listing.id)
        self.assertFalse(rent._coop_decree_block())
