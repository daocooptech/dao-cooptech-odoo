# -*- coding: utf-8 -*-
"""Решение 509: денежный заём гражданину — только КПК, СКПК, банк, МФО."""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLoan509(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Form = cls.env['coop.legal.form']
        Partner = cls.env['res.partner']
        cls.po = Partner.create({'name': 'ПО Проверки 509', 'is_company': True,
                                 'coop_legal_form_id': Form.search([('code', '=', 'po')], limit=1).id})
        cls.kpk = Partner.create({'name': 'КПК Проверки 509', 'is_company': True,
                                  'coop_legal_form_id': Form.search([('code', '=', 'kpk')], limit=1).id})
        cls.ooo = Partner.create({'name': 'ООО Проверки 509', 'is_company': True,
                                  'coop_legal_form_id': Form.search([('code', '=', 'ooo')], limit=1).id})

    def _money(self, owner, code, **terms):
        method = self.env['coop.resource.method'].search([('code', '=', code)], limit=1)
        resource = self.env['coop.resource'].create({
            'name': 'Деньги 509', 'listing_type': 'offer', 'resource_type': 'financial',
            'owner_id': owner.id, 'price': 100000,
            'method_ids': [(6, 0, method.ids)], 'state': 'draft'})
        resource.term_ids.write(dict({'price': 100000}, **terms))
        return [p for p in resource._coop_terms_problems() if 'денежный заём' in p]

    def test_po_ne_dayot_zaym_grazhdanam(self):
        self.assertTrue(self._money(self.po, 'rent'))
        self.assertTrue(self._money(self.po, 'free', free_mode='loan', free_to='any'))

    def test_po_mozhet_na_vremya_organizaciyam(self):
        self.assertFalse(self._money(self.po, 'free', free_mode='loan', free_to='org'))

    def test_kpk_i_mfo_dayut(self):
        self.assertFalse(self._money(self.kpk, 'rent'))
        self.assertTrue(self._money(self.ooo, 'rent'))
        self.ooo.coop_finance_license = 'mfo'
        self.assertFalse(self._money(self.ooo, 'rent'))
