# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCitySuggestions(TransactionCase):
    """Подсказка городов для поля «Город» (виджет `coop_city`)."""

    def test_known_cities_once_frequent_first(self):
        Partner = self.env['res.partner']
        for city in ('Пробоград', 'Пробоград', 'Пробоград', ' пробоград ', 'Малый Проб'):
            Partner.create({'name': 'Житель %s' % city, 'city': city})
        cities = Partner.coop_city_suggestions()
        self.assertEqual([c for c in cities if c.lower() == 'пробоград'], ['Пробоград'],
                         'один город — одна подсказка, без двойников по регистру и пробелам')
        self.assertIn('Малый Проб', cities)
        self.assertLess(cities.index('Пробоград'), cities.index('Малый Проб'),
                        'частый город — выше редкого')
