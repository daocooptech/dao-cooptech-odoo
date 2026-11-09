# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged

from odoo.addons.coop_resources.models.coop_resource_tree import (
    rebuild_category_tree)

ROOTS = [
    'Сырьё и материалы', 'Оборудование и станки', 'Инструмент',
    'Техника и транспорт', 'Недвижимость', 'Электроника и оргтехника',
    'Продовольствие и сельхозпродукция', 'Для дома и быта',
    'Вещи и экипировка',
]


@tagged('post_install', '-at_install')
class TestCategoryTree(TransactionCase):
    """Девять разделов материальных ресурсов (задача 396, решение 632)."""

    def _res(self, name, category):
        return self.env['coop.resource'].create({
            'name': name, 'listing_type': 'offer', 'resource_type': 'material',
            'owner_id': self.env.user.partner_id.id,
            'category_id': category.id})

    def _old(self, name):
        return self.env['coop.resource.category'].search(
            [('name', '=', name)], limit=1) or \
            self.env['coop.resource.category'].create({'name': name})

    def test_nine_roots_and_idempotent(self):
        rebuild_category_tree(self.env)
        Category = self.env['coop.resource.category']
        roots = Category.search([('parent_id', '=', False)]).mapped('name')
        for name in ROOTS:
            self.assertIn(name, roots)
        count = Category.search_count([])
        rebuild_category_tree(self.env)
        self.assertEqual(count, Category.search_count([]),
                         'повторный прогон не должен заводить категории')

    def test_old_category_with_records_moves_in_place(self):
        old = self._old('Ремонт и стройматериалы')
        resource = self._res('Цемент М500', old)
        rebuild_category_tree(self.env)
        self.assertEqual(resource.category_id.name, 'Стройматериалы')
        self.assertEqual(resource.category_id.parent_id.name,
                         'Сырьё и материалы')

    def test_keyword_rules(self):
        equipment = self._old('Оборудование для бизнеса')
        rent = self._res('Сдам бетономешалку на выходные', equipment)
        oven = self._res('Подовая печь, бывшая в употреблении', equipment)
        gen = self._res('Генератор на 5 кВт', equipment)
        rebuild_category_tree(self.env)
        self.assertEqual(rent.category_id.name, 'Инструмент в прокат')
        self.assertEqual(oven.category_id.name, 'Кухня и пекарня')
        self.assertEqual(gen.category_id.name, 'Энергия и насосы')

    def test_duplicate_old_category_is_merged(self):
        rebuild_category_tree(self.env)
        dup = self.env['coop.resource.category'].create(
            {'name': 'Ремонт и стройматериалы'})
        resource = self._res('Утеплитель минеральный', dup)
        rebuild_category_tree(self.env)
        self.assertFalse(dup.exists())
        self.assertEqual(resource.category_id.name, 'Стройматериалы')

    # ── Задача 398 ───────────────────────────────────────────────────────

    def _path(self, category):
        names = []
        while category:
            names.insert(0, category.name)
            category = category.parent_id
        return ' / '.join(names)

    def test_398_real_estate_split(self):
        old = self._old('Склады и коммерческая недвижимость')
        store = self._res('Помещение под временное хранение', old)
        office = self._res('Офис в бизнес-центре в аренду', old)
        rebuild_category_tree(self.env)
        self.assertEqual(self._path(store.category_id),
                         'Недвижимость / Коммерческая / Склады')
        self.assertEqual(self._path(office.category_id),
                         'Недвижимость / Коммерческая / Офисы')
        flat = self.env['coop.resource.category'].search(
            [('name', '=', 'Квартиры')])
        self.assertEqual(self._path(flat), 'Недвижимость / Жилая / Квартиры')

    def test_398_no_other_and_no_orphans(self):
        rebuild_category_tree(self.env)
        tractor = self._res('Мотоблок с навесным', self.env[
            'coop.resource.category'].search(
                [('name', '=', 'Оборудование и станки')], limit=1))
        tractor.category_id = False
        welder = self._res('Сдам сварочный аппарат', self.env[
            'coop.resource.category'])
        generic = self._res('Оборудование под нужды проекта, 1 шт.',
                            self.env['coop.resource.category'])
        rebuild_category_tree(self.env)
        self.assertEqual(tractor.category_id.name, 'Сельхозтехника')
        self.assertEqual(welder.category_id.name, 'Инструмент в прокат')
        self.assertEqual(generic.category_id.name, 'Оборудование и станки')
        self.assertFalse(self.env['coop.resource.category'].search(
            [('name', 'in', ['Прочее оборудование', 'Аренда спецтехники'])]))

    def test_398_labour_and_finance_leave_goods(self):
        rebuild_category_tree(self.env)
        warehouse = self.env['coop.resource.category'].search(
            [('name', '=', 'Склады')], limit=1)
        work = self.env['coop.resource'].create({
            'name': 'Разнорабочие на монтаж, 4 смены', 'listing_type': 'request',
            'resource_type': 'labour', 'owner_id': self.env.user.partner_id.id,
            'category_id': warehouse.id})
        fee = self.env['coop.resource'].create({
            'name': 'Гос. пошлина за регистрацию', 'listing_type': 'request',
            'resource_type': 'financial',
            'owner_id': self.env.user.partner_id.id})
        rebuild_category_tree(self.env)
        self.assertEqual(work.category_id.name, 'Работа и подряд')
        self.assertEqual(fee.category_id.name, 'Платежи и обязательные расходы')
