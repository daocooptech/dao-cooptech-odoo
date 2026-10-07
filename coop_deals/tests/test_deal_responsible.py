# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDealResponsible(TransactionCase):
    """Ответственный на каждую сторону сделки (решение 450)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.org = cls.env['res.partner'].create(
            {'name': 'ПК «Проба ответственных»', 'is_company': True})
        cls.head = cls._member('Руководитель Пробы', ['sign', 'represent'])
        cls.seller = cls._member('Первый Продавец', ['deal'])
        cls.second = cls._member('Второй Продавец', ['deal'])
        cls.clerk = cls._member('Делопроизводитель Пробы', ['publish'])
        cls.buyer = cls._user('Покупатель Пробы')

    @classmethod
    def _user(cls, name):
        return cls.env['res.users'].create({
            'name': name, 'login': name.replace(' ', '-').lower(),
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    @classmethod
    def _member(cls, name, codes):
        user = cls._user(name)
        cls.env['coop.membership'].create({
            'partner_id': user.partner_id.id,
            'organization_id': cls.org.id,
            'state': 'active',
            'admission_basis': 'Решение правления № 1',
            'power_ids': [(6, 0, cls.env['coop.power'].search([('code', 'in', codes)]).ids)],
        })
        return user

    def _deal(self, user=None):
        Deal = self.env['coop.deal'].with_user(user) if user else self.env['coop.deal'].sudo()
        return Deal.create({
            'name': 'Поставка семян',
            'party_a_id': self.org.id,
            'party_b_id': self.buyer.partner_id.id,
        })

    def test_defaults(self):
        deal = self._deal()
        self.assertIn(deal.responsible_a_id, self.seller | self.second)
        self.assertEqual(deal.responsible_b_id, self.buyer)
        own = self._deal(self.second)
        self.assertEqual(own.responsible_a_id, self.second)

    def test_only_own_side_assigns(self):
        deal = self._deal()
        with self.assertRaises(UserError):
            deal.with_user(self.buyer).write({'responsible_a_id': self.second.id})
        with self.assertRaises(UserError):
            deal.with_user(self.clerk).write({'responsible_a_id': self.second.id})
        deal.with_user(self.seller).write({'responsible_a_id': self.second.id})
        self.assertEqual(deal.responsible_a_id, self.second)
        with self.assertRaises(ValidationError):
            deal.with_user(self.seller).write({'responsible_a_id': self.clerk.id})

    def test_released_when_power_removed(self):
        deal = self._deal(self.seller)
        self.assertEqual(deal.responsible_a_id, self.seller)
        membership = self.env['coop.membership'].search([
            ('partner_id', '=', self.seller.partner_id.id),
            ('organization_id', '=', self.org.id)])
        membership.power_ids = [(5, 0, 0)]
        self.assertFalse(deal.responsible_a_id)
        todo = deal.activity_ids.filtered(lambda a: a.user_id == self.head)
        self.assertTrue(todo)
