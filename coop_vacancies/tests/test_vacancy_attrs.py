# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestVacancyAttrs(TransactionCase):
    """Поля по профессии у вакансии (№ 483)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.category = env['coop.specialization.category'].create(
            {'name': 'Проверка 483'})
        cls.driver = env['coop.specialization'].create(
            {'name': 'Водитель 483', 'category_id': cls.category.id})
        cls.cook = env['coop.specialization'].create(
            {'name': 'Повар 483', 'category_id': cls.category.id})
        cls.licence = env['coop.attribute'].create({
            'name': 'Права', 'code': 'x_licence483', 'value_type': 'tags',
            'option_ids': [(0, 0, {'name': 'B', 'code': 'b'}),
                           (0, 0, {'name': 'C', 'code': 'c'})]})
        cls.grade = env['coop.attribute'].create({
            'name': 'Разряд', 'code': 'x_grade483', 'value_type': 'integer',
            'value_min': 1, 'value_max': 8})
        env['coop.attribute.assignment'].create([
            {'attribute_id': cls.licence.id, 'specialization_id': cls.driver.id},
            {'attribute_id': cls.grade.id,
             'specialization_category_id': cls.category.id}])
        cls.vacancy = env['coop.vacancy'].create({
            'name': 'Водитель', 'partner_id': env.user.partner_id.id,
            'coop_specialization_id': cls.driver.id,
            'attrs': {'x_licence483': ['c'], 'x_grade483': 4},
            'state': 'published'})

    def test_definition_by_specialization(self):
        names = [i['name'] for i in self.driver.attribute_definition]
        self.assertEqual(set(names), {'x_licence483', 'x_grade483'})
        self.assertEqual([i['name'] for i in self.cook.attribute_definition],
                         ['x_grade483'])

    def test_new_option_reaches_definition(self):
        self.env['coop.attribute.option'].create({
            'attribute_id': self.licence.id, 'name': 'D', 'code': 'd'})
        item = next(i for i in self.driver.attribute_definition
                    if i['name'] == 'x_licence483')
        self.assertIn('d', [t[0] for t in item['tags']])

    def test_facts_and_counts(self):
        self.assertIn('Права', self.vacancy.attrs_facts)
        self.assertIn('C', self.vacancy.attrs_facts)
        domain = [('coop_specialization_category_id', '=', self.category.id),
                  ('coop_specialization_id', '=', self.driver.id)]
        blocks = self.env['coop.vacancy']._coop_catalog_filters(domain)
        block = next(b for b in blocks if b['code'] == 'attr_x_licence483')
        self.assertEqual({o['value']: o['count'] for o in block['options']},
                         {'b': 0, 'c': 1})
        found = self.env['coop.vacancy'].search(
            domain + [('attrs.x_licence483', 'in', ['c'])])
        self.assertEqual(found, self.vacancy)

    def test_no_professional_blocks_without_spec(self):
        blocks = self.env['coop.vacancy']._coop_catalog_filters([])
        self.assertFalse([b for b in blocks if b['code'].startswith('attr_')])

    def test_limits_and_guard(self):
        with self.assertRaises(ValidationError):
            self.vacancy.attrs = {'x_grade483': 12}
            self.env.flush_all()
        self.vacancy.invalidate_recordset()
        with self.assertRaises(ValidationError):
            self.licence.unlink()
