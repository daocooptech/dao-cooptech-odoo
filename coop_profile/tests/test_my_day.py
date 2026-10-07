# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMyDay(TransactionCase):
    """«Моя страница»: дела на сегодня и сделки, ждущие меня (решение 450)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.me = cls._user('Хозяин Страницы')
        cls.other = cls._user('Вторая Сторона Пробы')

    @classmethod
    def _user(cls, name):
        return cls.env['res.users'].create({
            'name': name, 'login': name.replace(' ', '-').lower(),
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    def _deal(self, author, state):
        deal = self.env['coop.deal'].with_user(author).sudo().create({
            'name': 'Проба', 'party_a_id': self.me.partner_id.id,
            'party_b_id': self.other.partner_id.id, 'state': state,
            'author_id': author.partner_id.id,
        })
        return deal

    def test_waiting_and_activities(self):
        incoming = self._deal(self.other, 'lead')
        mine = self._deal(self.me, 'lead')
        accept = self._deal(self.other, 'acceptance')
        accept.act_confirmed_b = True
        incoming.activity_schedule('mail.mail_activity_data_call', user_id=self.me.id,
                                   summary='Перезвонить')
        page = self.me.partner_id.with_user(self.me)
        self.assertIn(incoming, page.coop_waiting_deal_ids)
        self.assertIn(accept, page.coop_waiting_deal_ids)
        self.assertNotIn(mine, page.coop_waiting_deal_ids)
        self.assertEqual(page.coop_my_activity_count, 1)
        # Чужая страница — без полос.
        foreign = self.other.partner_id.with_user(self.me)
        self.assertFalse(foreign.coop_waiting_deal_ids)
        self.assertFalse(foreign.coop_my_activity_count)
