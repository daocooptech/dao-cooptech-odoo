# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWallAttach(TransactionCase):
    """№ 454: к посту стены — запись из уместного каталога."""

    def setUp(self):
        super().setUp()
        if 'coop.event' not in self.env:
            self.skipTest('нет каталога событий')
        self.me = self.env.user.partner_id
        self.event = self.env['coop.event'].create({
            'name': 'Субботник у мастерской', 'organizer_id': self.me.id,
            'date_start': fields.Datetime.now()})
        self.other = self.env['res.partner'].create({'name': 'Чужая страница'})
        self.post = self.me.message_post(
            body='Приходите', message_type='comment',
            subtype_xmlid='mail.mt_comment', author_id=self.me.id)

    def test_kinds_and_search(self):
        Message = self.env['mail.message']
        kinds = [k['id'] for k in Message.coop_attach_kinds('res.partner', self.me.id)]
        self.assertIn('event', kinds)
        found = Message.coop_attach_search('res.partner', self.me.id, 'event', 'Субботник')
        self.assertEqual([r['id'] for r in found], [self.event.id])
        self.assertEqual(Message.coop_attach_kinds('mail.channel', 1), [])

    def test_attach_and_card(self):
        card = self.env['mail.message'].coop_attach_set(
            self.post.id, 'coop.event', self.event.id)
        self.assertEqual(card['title'], self.event.display_name)
        self.assertEqual(card['icon'], 'event')
        self.assertEqual(self.post._coop_rec_data()['id'], self.event.id)

    def test_only_fitting_record(self):
        # Событие чужого организатора к своей стене не прикрепить.
        alien = self.env['coop.event'].create({
            'name': 'Чужое', 'organizer_id': self.other.id,
            'date_start': fields.Datetime.now()})
        with self.assertRaises(UserError):
            self.env['mail.message'].coop_attach_set(
                self.post.id, 'coop.event', alien.id)

    def test_gone_record_is_hidden(self):
        self.env['mail.message'].coop_attach_set(
            self.post.id, 'coop.event', self.event.id)
        self.event.unlink()
        self.assertEqual(self.post._coop_rec_data(), {'hidden': True})
