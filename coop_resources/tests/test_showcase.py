# -*- coding: utf-8 -*-
import base64

from lxml import etree

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged

# Красный квадрат 1×1 — самый маленький настоящий снимок.
PIXEL = base64.b64encode(bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108020000009077'
    '53de0000000c4944415408d763f8cfc0000003010100c9fe92ef0000000049'
    '454e44ae426082')).decode()


@tagged('post_install', '-at_install')
class TestResourceShowcase(TransactionCase):
    """Вёрстка и снимки витрины ресурса (`ResourcePage`, задача 397)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls._user('Хозяин Снимков')
        cls.stranger = cls._user('Гость Снимков')
        cls.resource = cls.env['coop.resource'].create({
            'name': 'Мёд липовый', 'owner_id': cls.owner.partner_id.id,
            'image_1920': PIXEL, 'state': 'published'})

    @classmethod
    def _user(cls, name):
        return cls.env['res.users'].create({
            'name': name, 'login': name.replace(' ', '-').lower(),
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

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

    def test_gallery_main_first(self):
        """Главный снимок — первым, за ним остальные по порядку."""
        Image = self.env['coop.resource.image']
        second = Image.create({'resource_id': self.resource.id, 'sequence': 2, 'image_1920': PIXEL})
        first = Image.create({'resource_id': self.resource.id, 'sequence': 1, 'image_1920': PIXEL})
        self.resource.invalidate_recordset()
        data = self.resource.gallery_data
        self.assertEqual([d['id'] for d in data], ['main', first.id, second.id])
        self.assertIn('/web/image/coop.resource/%s/image_1920' % self.resource.id, data[0]['src'])
        self.assertIn('image_256', data[1]['thumb'])
        self.assertEqual(self.resource.image_count, 3)

    def test_gallery_on_showcase(self):
        """На витрине — виджет галереи на `gallery_data`."""
        nodes = self._arch().xpath("//field[@name='gallery_data']")
        self.assertTrue(nodes)
        self.assertEqual(nodes[0].get('widget'), 'coop_gallery')

    def test_gallery_limit(self):
        """Дополнительных снимков не больше восьми."""
        Image = self.env['coop.resource.image']
        Image.create([{'resource_id': self.resource.id, 'image_1920': PIXEL}] * 8)
        with self.assertRaises(ValidationError):
            Image.create({'resource_id': self.resource.id, 'image_1920': PIXEL})

    def test_gallery_rights(self):
        """Снимки добавляет хозяин; чужой — только смотрит."""
        Image = self.env['coop.resource.image']
        mine = Image.with_user(self.owner).create(
            {'resource_id': self.resource.id, 'image_1920': PIXEL})
        self.assertTrue(mine.with_user(self.stranger).read(['image_256']))
        with self.assertRaises(AccessError):
            Image.with_user(self.stranger).create(
                {'resource_id': self.resource.id, 'image_1920': PIXEL})
        with self.assertRaises(AccessError):
            mine.with_user(self.stranger).unlink()
