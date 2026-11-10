# -*- coding: utf-8 -*-
"""Опт и розница: ступени, хранимые признаки, единицы с модерацией (задача 401, решение 634)."""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWholesale(TransactionCase):

    def _sale(self, **terms):
        method = self.env['coop.resource.method'].search([('code', '=', 'sale')], limit=1)
        resource = self.env['coop.resource'].create({
            'name': 'Тест опта', 'listing_type': 'offer', 'resource_type': 'material',
            'owner_id': self.env.user.partner_id.id,
            'price': 1000, 'method_ids': [(6, 0, method.ids)], 'state': 'draft'})
        term = resource.term_ids.filtered(lambda t: t.code == 'sale')
        term.write(dict({'price': 1000}, **terms))
        return resource, term

    def test_no_tiers_means_no_wholesale(self):
        resource, _term = self._sale(min_qty=5)
        self.assertFalse(resource.has_wholesale)
        self.assertEqual(resource.min_batch, 5)

    def test_tiers_set_flags_and_display(self):
        resource, term = self._sale(
            min_qty=5, price_unit_label='кг', bulk_qty=10, bulk_price=900,
            bulk2_qty=50, bulk2_price=800)
        self.assertTrue(resource.has_wholesale)
        self.assertEqual(resource.wholesale_price, 800)
        self.assertEqual(term._coop_tiers(), [(10, 900), (50, 800)])
        self.assertIn('800', resource.wholesale_display)
        self.assertIn('/кг', resource.wholesale_display)
        found = self.env['coop.resource'].search(
            [('id', '=', resource.id), ('has_wholesale', '=', True)])
        self.assertEqual(found, resource)

    def test_tier_needs_both_fields(self):
        _resource, term = self._sale()
        with self.assertRaises(UserError):
            term.write({'bulk_qty': 10})

    def test_tiers_must_go_up_and_cheaper(self):
        _resource, term = self._sale()
        with self.assertRaises(UserError):
            term.write({'bulk_qty': 10, 'bulk_price': 900,
                        'bulk2_qty': 50, 'bulk2_price': 950})
        with self.assertRaises(UserError):
            term.write({'bulk_qty': 10, 'bulk_price': 900,
                        'bulk2_qty': 5, 'bulk2_price': 800})

    def test_wholesale_not_before_min_batch(self):
        _resource, term = self._sale()
        with self.assertRaises(UserError):
            term.write({'min_qty': 20, 'bulk_qty': 10, 'bulk_price': 900})

    def test_own_unit_goes_to_moderation(self):
        Uom = self.env['coop.resource.uom']
        unit = Uom.coop_propose('  бухта   кабеля ')
        self.assertEqual(unit, {'name': 'бухта кабеля', 'proposed': True})
        # Повтор с другим регистром — та же единица, не двойник.
        again = Uom.coop_propose('БУХТА КАБЕЛЯ')
        self.assertEqual(again['name'], 'бухта кабеля')
        self.assertEqual(len(Uom.search([]).filtered(
            lambda u: u.name.casefold() == 'бухта кабеля')), 1)
        # Автору видна сразу; после одобрения — всем.
        self.assertIn('бухта кабеля', [u['name'] for u in Uom.coop_choices()])
        Uom.search([('name', '=', 'бухта кабеля')]).action_approve()
        self.assertFalse(Uom.coop_propose('бухта кабеля')['proposed'])

    def test_existing_unit_is_not_proposed(self):
        unit = self.env['coop.resource.uom'].coop_propose('кг')
        self.assertFalse(unit['proposed'])
