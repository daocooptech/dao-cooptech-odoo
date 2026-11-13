# -*- coding: utf-8 -*-
"""Слайдеры фото и видео во всех каталогах (задача 444)."""
from lxml import etree

from odoo.tests import TransactionCase, tagged

from odoo.addons.coop_demo.data import load_media_gallery as gallery


@tagged('post_install', '-at_install')
class TestMediaGallery(TransactionCase):

    def test_every_catalog_form_has_slider(self):
        """Раздел с лентой фото — со слайдером на форме."""
        for model in gallery._models(self.env):
            # У организации своя форма, не общая форма контакта.
            view = self.env.ref('coop_orgs.view_coop_orgs_form').id \
                if model == 'res.partner' else None
            arch = self.env[model].get_view(view, 'form')['arch']
            found = etree.fromstring(arch).xpath(
                "//field[@name='coop_media_data'][@widget='coop_media']")
            self.assertTrue(found, model)
        for model in ('coop.warehouse.offer', 'coop.auction', 'res.partner'):
            self.assertIn(model, gallery._models(self.env))

    def test_demo_records_have_three_to_six(self):
        """У демо-записей — 3–6 медиа, снимки в ленте разные."""
        self.assertEqual(gallery.load_media_gallery(self.env), 0, 'повторный прогон что-то создал')
        for model in gallery._models(self.env):
            records = gallery._records(self.env, model)[:40]
            for record in records:
                data = record.coop_media_data
                items = data['photos'] + data['videos']
                self.assertGreaterEqual(len(items), 3, '%s %s' % (model, record.id))
                self.assertLessEqual(len(items), 6, '%s %s' % (model, record.id))
            media = self.env['coop.media'].search([
                ('res_model', '=', model), ('res_id', 'in', records.ids), ('kind', '=', 'photo')])
            for rid in set(media.mapped('res_id')):
                sums = [m.image_1920 for m in media if m.res_id == rid]
                self.assertEqual(len(sums), len(set(sums)), '%s %s: копии в ленте' % (model, rid))

    def test_new_record_gets_empty_slider(self):
        """Новая запись: слайдер есть сразу — пустой, с «+»."""
        for model in gallery._models(self.env):
            data = self.env[model].new({}).coop_media_data
            self.assertEqual(data['photos'] + data['videos'], [], model)
            self.assertTrue(data['can_add'], model)
