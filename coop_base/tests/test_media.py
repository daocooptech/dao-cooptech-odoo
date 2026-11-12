# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.coop_base.models.coop_media import video_embed


@tagged('post_install', '-at_install')
class TestMedia(TransactionCase):
    """Фото и видео записей (`coop.media`, задача 424, решение 654)."""

    def test_video_links(self):
        cases = {
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5': 'https://www.youtube.com/embed/dQw4w9WgXcQ',
            'https://youtu.be/dQw4w9WgXcQ': 'https://www.youtube.com/embed/dQw4w9WgXcQ',
            'https://youtube.com/shorts/dQw4w9WgXcQ': 'https://www.youtube.com/embed/dQw4w9WgXcQ',
            'https://rutube.ru/video/0123456789abcdef0123456789abcdef/':
                'https://rutube.ru/play/embed/0123456789abcdef0123456789abcdef',
            'https://vk.com/video-22822305_456242393':
                'https://vk.com/video_ext.php?oid=-22822305&id=456242393&hd=2',
            'https://vkvideo.ru/video-22822305_456242393':
                'https://vk.com/video_ext.php?oid=-22822305&id=456242393&hd=2',
        }
        for url, embed in cases.items():
            self.assertEqual(video_embed(url), (embed, 'embed'), url)
        self.assertEqual(video_embed('https://cdn.example.org/clip.mp4'),
                         ('https://cdn.example.org/clip.mp4', 'file'))
        self.assertEqual(video_embed('https://example.org/page'), (False, False))

    def test_bad_link_refused(self):
        partner = self.env['res.partner'].create({'name': 'Запись'})
        with self.assertRaises(ValidationError):
            self.env['coop.media'].create({
                'res_model': 'res.partner', 'res_id': partner.id,
                'kind': 'video', 'video_url': 'https://example.org/page'})
