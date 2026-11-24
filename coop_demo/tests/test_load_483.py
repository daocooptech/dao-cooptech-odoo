# -*- coding: utf-8 -*-
"""№ 483: дробление рубрик, свои наборы у листов, согласованные значения."""
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.coop_demo.data import load_483


@tagged('post_install', '-at_install')
class TestLoad483(TransactionCase):

    def _cat(self, full_name):
        return self.env['coop.resource.category'].search(
            [('complete_name', '=', full_name)], limit=1)

    def _res(self, name, category):
        return self.env['coop.resource'].create({
            'name': name, 'listing_type': 'offer', 'resource_type': 'material',
            'owner_id': self.env.user.partner_id.id,
            'category_id': category.id})

    def test_split_moves_by_title_and_keeps_rest(self):
        parent = self._cat('Сырьё и материалы / Стройматериалы')
        self.assertTrue(parent)
        cement = self._res('Цемент М500, 40 мешков', parent)
        rebar = self._res('Арматура А500 12 мм', parent)
        odd = self._res('Что-то для стройки', parent)
        load_483.load_483(self.env)
        self.assertEqual(cement.category_id.name, 'Строительные смеси')
        self.assertEqual(rebar.category_id.name, 'Металлопрокат')
        self.assertEqual(odd.category_id.name, 'Прочие стройматериалы')
        self.assertEqual(load_483._current(cement).get('strength'), 'm500')

    def test_idempotent(self):
        load_483.load_483(self.env)
        Category = self.env['coop.resource.category']
        count = Category.search_count([])
        load_483.load_483(self.env)
        self.assertEqual(count, Category.search_count([]))

    def test_leaf_sets_differ(self):
        load_483.load_483(self.env)
        flat = self._cat('Недвижимость / Жилая / Квартиры')
        land = self._cat('Недвижимость / Земельные участки')
        codes = lambda c: {d['name'] for d in c.attribute_definition}  # noqa
        self.assertIn('flat_market', codes(flat))
        self.assertNotIn('flat_market', codes(land))
        build = self._cat('Сырьё и материалы / Стройматериалы')
        self.assertNotIn('rolled_kind', codes(build))

    def test_agree_fixes_contradictions(self):
        load_483.load_483(self.env)
        options = {a.code: {o.name: o.code for o in a.option_ids}
                   for a in self.env['coop.attribute'].search([])}
        res = self.env['coop.resource'].new({'name': 'Отдам старый шкаф'})
        cur = {'condition': options['condition']['Новое'],
               'flat_market': options['flat_market']['Новостройка'],
               'build_year': 1987, 'capacity_ton': 40.0, 'gvw_t': 12.0}
        import random
        fix = load_483._agree(cur, res, 'Техника и транспорт / Грузовики и '
                              'автобусы / Грузовики', random.Random(1), options)
        self.assertEqual(fix['condition'], options['condition']['Рабочее'])
        self.assertGreaterEqual(fix['build_year'], 2019)
        self.assertLessEqual(fix['capacity_ton'], 25)
        self.assertGreater(fix['gvw_t'], fix['capacity_ton'])
