# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWarehouseFilters(TransactionCase):
    """№ 438: у «Моих складов» своя панель фильтров, а не строка «пока
    отбирают порядком»."""

    def test_blocks(self):
        blocks = self.env['coop.warehouse']._coop_catalog_filters([])
        codes = [b['code'] for b in blocks]
        self.assertEqual(codes, ['storage', 'city', 'unit', 'free', 'quick'])
        quick = blocks[-1]['options']
        for option in quick:
            # Домен быстрого отбора должен читаться движком.
            self.env['coop.warehouse'].search_count(option['domain'])
