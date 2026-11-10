# -*- coding: utf-8 -*-
from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResourceShowcase(TransactionCase):
    """Вёрстка витрины ресурса (`ResourcePage`, задача 397)."""

    def _arch(self):
        views = self.env['coop.resource'].get_views(
            [(self.env.ref('coop_resources.view_coop_resource_form').id, 'form')])
        return etree.fromstring(views['views']['form']['arch'])

    def test_conditions_stacked(self):
        """«Условия» — группами друг под другом: в две колонки метки
        второй группы наезжали на значения первой (владелец 10.11.2026)."""
        block = self._arch().xpath("//section[h2='Условия']")
        self.assertTrue(block, 'нет блока «Условия»')
        self.assertEqual(block[0].xpath('./group')[0].get('col'), '1')
