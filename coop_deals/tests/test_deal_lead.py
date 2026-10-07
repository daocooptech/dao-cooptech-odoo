# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDealLead(TransactionCase):
    """Обращение — первая стадия сделки (решение 451)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls._user('Владелец Объявления')
        cls.buyer = cls._user('Откликнувшийся Покупатель')
        cls.stranger = cls._user('Посторонний Участник')
        cls.listing = cls.env['coop.resource'].create({
            'name': 'Мёд гречишный, 10 кг',
            'listing_type': 'offer',
            'owner_id': cls.owner.partner_id.id,
            'price': 6000,
        })

    @classmethod
    def _user(cls, name):
        return cls.env['res.users'].create({
            'name': name, 'login': name.replace(' ', '-').lower(),
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    def _respond(self):
        wizard = self.env['coop.resource.respond'].with_user(self.buyer).create(
            {'resource_id': self.listing.id, 'note': 'Заберу в субботу.'})
        action = wizard.action_respond()
        return self.env['coop.deal'].browse(action['res_id'])

    def test_respond_makes_lead(self):
        deal = self._respond()
        self.assertEqual(deal.state, 'lead')
        self.assertEqual(deal.party_a_id, self.owner.partner_id)
        self.assertEqual(deal.party_b_id, self.buyer.partner_id)
        self.assertEqual(deal.amount, 6000)

    def test_lead_to_negotiations(self):
        deal = self._respond()
        deal.with_user(self.owner).action_negotiate()
        self.assertEqual(deal.state, 'draft')
        with self.assertRaises(UserError):
            deal.with_user(self.owner).action_negotiate()

    def test_lead_declined_or_foreign(self):
        deal = self._respond()
        with self.assertRaises((AccessError, UserError)):
            deal.with_user(self.stranger).action_negotiate()
        deal.with_user(self.owner).action_cancel()
        self.assertEqual(deal.state, 'cancelled')

    def test_default_stays_negotiations(self):
        deal = self.env['coop.deal'].create({
            'name': 'Поставка льна',
            'party_a_id': self.owner.partner_id.id,
            'party_b_id': self.buyer.partner_id.id,
        })
        self.assertEqual(deal.state, 'draft')
