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

    def test_add_page(self):
        """«Добавить навык» заводит черновик от своего имени; опыт годами и
        месяцами пишется в месяцы; заготовку не публикуют (`SkillAddPage`)."""
        Offer = self.env['coop.skill.offer'].with_user(self.owner)
        action = Offer.action_new_offer()
        draft = Offer.browse(action['res_id'])
        self.assertEqual(draft.state, 'draft')
        self.assertEqual(draft.partner_id, self.owner.partner_id)
        self.assertIn(self.owner.partner_id, draft.coop_publisher_ids)
        self.assertEqual(action['view_id'][0] if isinstance(action['view_id'], (list, tuple))
                         else action['view_id'],
                         self.env.ref('coop_skills.view_coop_skill_add').id)
        draft.write({'experience_years': 3, 'experience_rest_months': 2})
        self.assertEqual(draft.experience_months, 38)
        self.assertEqual((draft.experience_years, draft.experience_rest_months), (3, 2))
        partner_cls = type(self.env['res.partner'])
        with patch.object(partner_cls, 'coop_require_level', return_value=True):
            with self.assertRaises(UserError):
                draft.action_publish()
            draft.name = 'Кровельщик'
            draft.action_publish()
        self.assertEqual(draft.state, 'published')
