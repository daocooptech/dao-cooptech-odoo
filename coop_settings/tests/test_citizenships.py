# -*- coding: utf-8 -*-
"""Список гражданств ведёт прежние поля резидентства (задача 400, решение 640)."""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCitizenships(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ru, self.kz = self.env.ref('base.ru'), self.env.ref('base.kz')
        self.partner = self.env['res.partner'].create({'name': 'Гражданин'})

    def test_list_sets_first_citizenship_and_residency(self):
        self.partner.coop_citizenship_ids = [(6, 0, [self.kz.id, self.ru.id])]
        self.assertEqual(self.partner.coop_citizenship_id, self.kz)
        self.assertTrue(self.partner.coop_fx_resident)

    def test_foreigner_without_permit_is_not_resident(self):
        self.partner.coop_citizenship_ids = [(6, 0, [self.kz.id])]
        self.assertFalse(self.partner.coop_fx_resident)
        self.assertFalse(self.partner.coop_is_ru_resident())
        self.partner.coop_ru_residence_permit = True
        self.assertTrue(self.partner.coop_fx_resident)

    def test_manual_mark_in_same_write_is_kept(self):
        self.partner.write({'coop_citizenship_ids': [(6, 0, [self.ru.id])],
                            'coop_fx_resident': False})
        self.assertFalse(self.partner.coop_fx_resident)

    def test_empty_list_falls_back_to_old_mark(self):
        self.partner.coop_fx_resident = False
        self.assertFalse(self.partner.coop_is_ru_resident())
        self.partner.coop_fx_resident = True
        self.assertTrue(self.partner.coop_is_ru_resident())
