# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWallPost(TransactionCase):
    """Лента страницы: пишет только хозяин (решение 653)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group = cls.env.ref('base.group_user').id
        cls.me, cls.guest = (cls.env['res.users'].create({
            'name': name, 'login': login, 'group_ids': [(6, 0, [group])],
        }) for name, login in (('Хозяин Стены', 'wall-owner'), ('Гость Стены', 'wall-guest')))

    def test_owner_posts_guest_does_not(self):
        page = self.me.partner_id
        page.with_user(self.me).message_post(body='Моя запись', message_type='comment')
        with self.assertRaises(AccessError):
            page.with_user(self.guest).message_post(body='Чужая запись', message_type='comment')

    def test_guest_blocked_through_sudo(self):
        # Поле ленты публикует через `sudo()` (`/mail/message/post`), № 462.
        page = self.me.partner_id
        with self.assertRaises(AccessError):
            page.with_user(self.guest).sudo().message_post(body='Мимо поля', message_type='comment')
        page.with_user(self.me).sudo().message_post(body='Своё через поле', message_type='comment')

    def test_engine_notices_pass(self):
        page = self.me.partner_id
        # Служебное извещение гостя и запись суперпользователя — как прежде.
        page.with_user(self.guest).sudo().message_post(body='Извещение гостя')
        page.message_post(body='От платформы', message_type='comment')
        page.message_post(body='Извещение', message_type='notification')
