# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOfferOwner(TransactionCase):
    """Публикует и приостанавливает предложение только разместивший."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls._user('Мастер Пробы')
        cls.stranger = cls._user('Посетитель Пробы')
        cls.offer = cls.env['coop.skill.offer'].create({
            'name': 'Ремонт крыш', 'partner_id': cls.owner.partner_id.id,
            'state': 'published'})

    @classmethod
    def _user(cls, name):
        return cls.env['res.users'].create({
            'name': name, 'login': name.replace(' ', '-').lower(),
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    def test_only_owner(self):
        self.assertTrue(self.offer.with_user(self.owner).coop_is_mine)
        self.assertFalse(self.offer.with_user(self.stranger).coop_is_mine)
        with self.assertRaises((UserError, AccessError)):
            self.offer.with_user(self.stranger).action_pause()
        self.offer.with_user(self.owner).action_pause()
        self.assertEqual(self.offer.state, 'paused')
        partner_cls = type(self.env['res.partner'])
        with patch.object(partner_cls, 'coop_require_level', return_value=True):
            self.offer.with_user(self.owner).action_publish()
        self.assertEqual(self.offer.state, 'published')
