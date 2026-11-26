# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReview490(TransactionCase):
    """Одиночный отзыв раскрывается через 14 дней (490), оспаривание (491)."""

    def setUp(self):
        super().setUp()
        group = self.env.ref('base.group_user').id
        self.user_a, self.user_b = [self.env['res.users'].create({
            'name': name, 'login': login, 'group_ids': [(6, 0, [group])],
        }) for name, login in (('Сторона А 490', 'rev490-a'), ('Сторона Б 490', 'rev490-b'))]
        self.deal = self.env['coop.deal'].create({
            'name': 'Проба отзыва 490',
            'party_a_id': self.user_a.partner_id.id,
            'party_b_id': self.user_b.partner_id.id,
        })
        self.today = fields.Date.context_today(self.deal)
        self.deal.write({'state': 'done', 'closed_on': self.today - timedelta(days=15)})
        self.review = self.env['coop.deal.review'].create({
            'deal_id': self.deal.id,
            'author_id': self.user_a.partner_id.id,
            'target_id': self.user_b.partner_id.id,
            'rating': '1', 'body': 'Сорвал срок',
        })

    def test_single_review_opens_after_14_days(self):
        self.assertFalse(self.review.visible)
        self.assertEqual(self.user_b.partner_id.coop_deals_reviewed, 0,
                         'скрытый отзыв в доверие не идёт')
        self.env['coop.deal']._cron_open_single_reviews()
        self.assertTrue(self.review.visible)
        self.assertEqual(self.deal.reviews_opened_on, self.today)
        self.assertEqual(self.user_b.partner_id.coop_deals_reviewed, 1)
        self.assertEqual(self.user_b.partner_id.coop_trust, 0)

    def test_fresh_deal_stays_hidden(self):
        self.deal.closed_on = self.today - timedelta(days=3)
        self.env['coop.deal']._cron_open_single_reviews()
        self.assertFalse(self.review.visible)

    def test_dispute_by_target_only_and_text_kept(self):
        self.env['coop.deal']._cron_open_single_reviews()
        self.assertFalse(self.review.with_user(self.user_a).can_dispute)
        with self.assertRaises(UserError):
            self.review.with_user(self.user_a)._coop_dispute('не моё')
        mine = self.review.with_user(self.user_b)
        self.assertTrue(mine.can_dispute)
        mine._coop_dispute('Срок сдвинули по согласию')
        self.assertEqual(self.review.disputed_on, self.today)
        self.assertEqual(self.review.body, 'Сорвал срок')
        self.assertFalse(mine.can_dispute, 'второй раз не оспаривают')
        with self.assertRaises(UserError):
            self.review.write({'body': 'другое'})

    def test_dispute_window_closes(self):
        self.env['coop.deal']._cron_open_single_reviews()
        self.deal.reviews_opened_on = self.today - timedelta(days=15)
        self.assertFalse(self.review.with_user(self.user_b).can_dispute)
