# -*- coding: utf-8 -*-
"""Лента проекта — не рассылка (владелец 15.11.2026): пост остаётся в
ленте, уведомление — только отмеченным через @, во «Входящие»."""
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestProjectFeed(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = new_test_user(cls.env, 'feed_author', groups='base.group_user,project.group_project_user')
        cls.follower = new_test_user(cls.env, 'feed_follower', groups='base.group_user')
        cls.mentioned = new_test_user(cls.env, 'feed_mentioned', groups='base.group_user')
        (cls.follower | cls.mentioned).write({'notification_type': 'email'})
        cls.project = cls.env['project.project'].create({'name': 'Лента без рассылки'})
        cls.project.message_subscribe(partner_ids=(cls.follower | cls.mentioned).partner_id.ids)

    def _post(self, **kw):
        return self.project.message_post(
            body='Пост', author_id=self.author.partner_id.id,
            message_type='comment', subtype_xmlid='mail.mt_comment', **kw)

    def test_plain_post_notifies_nobody(self):
        message = self._post()
        self.assertFalse(message.notification_ids)

    def test_mention_goes_to_inbox(self):
        message = self._post(partner_ids=self.mentioned.partner_id.ids)
        self.assertEqual(message.notification_ids.res_partner_id, self.mentioned.partner_id)
        self.assertEqual(message.notification_ids.notification_type, 'inbox')
