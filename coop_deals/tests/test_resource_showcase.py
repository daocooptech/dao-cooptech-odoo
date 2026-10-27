# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResourceShowcase(TransactionCase):
    """Витрина ресурса (`ResourcePage`, решение 625): способ переключателем,
    слова состава поиском, отзывы о владельце."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls._user('Хозяин Пасеки')
        cls.buyer = cls._user('Покупатель Мёда')
        cls.buyer.partner_id.city = 'Сочи'
        Method = cls.env['coop.resource.method']
        cls.sale = Method.search([('code', '=', 'sale')], limit=1)
        cls.free = Method.search([('code', '=', 'free')], limit=1)
        cls.listing = cls.env['coop.resource'].create({
            'name': 'Мёд липовый',
            'listing_type': 'offer',
            'owner_id': cls.owner.partner_id.id,
            'price': 600,
            'method_ids': [(6, 0, (cls.sale | cls.free).ids)],
            'material_word_ids': [(0, 0, {'name': 'вощина '})],
        })
        cls.listing._coop_sync_terms()
        cls.listing.term_ids.filtered(lambda t: t.method_id == cls.sale).write(
            {'price': 650, 'price_unit_label': 'кг', 'prepay_pct': 50})

    @classmethod
    def _user(cls, name):
        return cls.env['res.users'].create({
            'name': name, 'login': name.replace(' ', '-').lower(),
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    def test_way_cards_follow_method(self):
        cards = {c['code']: c for c in self.listing.with_user(self.buyer).way_cards}
        self.assertEqual(cards['sale']['cta'], 'Купить в один клик')
        self.assertEqual(cards['sale']['price'], '650 ₽ / кг')
        # Цена крупно над условиями — в условиях её второй раз нет.
        self.assertEqual(cards['sale']['terms'], 'предоплата 50 %')
        self.assertEqual(cards['free']['cta'], 'Принять в дар')
        self.assertEqual(cards['free']['price'], 'даром')

    def test_respond_opens_on_chosen_method(self):
        action = self.listing.with_user(self.buyer).with_context(
            coop_method_id=self.free.id).action_respond()
        self.assertEqual(action['context']['default_method_id'], self.free.id)
        self.assertTrue(action['name'].startswith('Принять в дар'))
        # Чужой способ из контекста не подставляется.
        other = self.env['coop.resource.method'].search([('code', '=', 'rent')], limit=1)
        action = self.listing.with_user(self.buyer).with_context(
            coop_method_id=other.id).action_respond()
        self.assertNotIn('default_method_id', action['context'])

    def test_word_opens_catalog_in_viewer_city(self):
        word = self.listing.material_word_ids
        self.assertEqual(word.name, 'Вощина')
        action = self.listing.with_user(self.buyer).action_find_word(word.id)
        self.assertEqual(action['context']['search_default_name'], 'Вощина')
        self.assertEqual(action['context']['search_default_city'], 'Сочи')
        # Контекст каталога остаётся: это тот же экран, не другой.
        self.assertTrue(action['context'].get('coop_catalog'))

    def test_owner_reviews_only_disclosed(self):
        deal = self.env['coop.deal'].create({
            'name': 'Мёд, 10 кг',
            'party_a_id': self.owner.partner_id.id,
            'party_b_id': self.buyer.partner_id.id,
        })
        # Отзыв пишут только по завершённой сделке.
        deal.sudo().state = 'done'
        Review = self.env['coop.deal.review'].sudo()
        Review.create({'deal_id': deal.id, 'side': 'b', 'rating': '4', 'body': 'Мёд хороший.',
                       'author_id': self.buyer.partner_id.id, 'target_id': self.owner.partner_id.id})
        self.listing.invalidate_recordset()
        # Вторая сторона ещё не высказалась — первый отзыв не виден никому.
        self.assertEqual(self.listing.with_user(self.buyer).owner_review_count, 0)
        Review.create({'deal_id': deal.id, 'side': 'a', 'rating': '5',
                       'author_id': self.owner.partner_id.id, 'target_id': self.buyer.partner_id.id})
        self.listing.invalidate_recordset()
        showcase = self.listing.with_user(self.buyer)
        self.assertEqual(showcase.owner_review_count, 1)
        self.assertIn('Мёд хороший.', showcase.owner_reviews_html)
        self.assertIn('1 отзыв по сделкам', showcase.owner_reviews_html)
