# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CoopResourceImage(models.Model):
    """Дополнительный снимок объявления — лента под главным снимком.

    Дизайн-система, `Gallery`: «большой снимок 4:3, под ним до пяти
    миниатюр». Владелец 10.11.2026: «под главным фото сделай снизу
    слайдер из маленьких фото 2–5 в зависимости от разрешения». Главный
    снимок остаётся `image_1920` самого объявления — он же стоит на
    карточке каталога; здесь только остальные.
    """
    _name = 'coop.resource.image'
    _description = 'Снимок объявления'
    _order = 'sequence, id'

    resource_id = fields.Many2one(
        'coop.resource', string='Объявление', required=True,
        ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Подпись')
    image_1920 = fields.Image(string='Снимок', required=True,
                              max_width=1920, max_height=1920)
    image_256 = fields.Image(related='image_1920', max_width=256,
                             max_height=256, store=True)

    MAX_PER_RESOURCE = 8

    @api.constrains('resource_id')
    def _check_limit(self):
        for resource in self.resource_id:
            if len(resource.image_ids) > self.MAX_PER_RESOURCE:
                raise ValidationError(
                    'У объявления не больше %s дополнительных снимков.'
                    % self.MAX_PER_RESOURCE)


class CoopResource(models.Model):
    _inherit = 'coop.resource'

    image_ids = fields.One2many(
        'coop.resource.image', 'resource_id', string='Ещё снимки',
        help='Показываются лентой под главным снимком.')
    image_count = fields.Integer(
        string='Снимков', compute='_compute_image_count')
    # Адреса снимков для витрины (`coop_gallery`): главный первым, за ним
    # остальные. Собирает сервер — виджету не нужно грузить связанные
    # записи, а адреса с `unique` не залипают в кэше браузера после замены.
    gallery_data = fields.Json(
        string='Снимки для витрины', compute='_compute_gallery_data')

    @api.depends('image_1920', 'image_ids')
    def _compute_image_count(self):
        for record in self:
            record.image_count = (1 if record.image_1920 else 0) + len(record.image_ids)

    @api.depends('image_1920', 'image_ids', 'image_ids.image_1920', 'name')
    def _compute_gallery_data(self):
        for record in self:
            images = []
            if record.image_1920 and record.id:
                stamp = int(record.write_date.timestamp()) if record.write_date else 0
                base = '/web/image/coop.resource/%s/' % record.id
                images.append({
                    'id': 'main',
                    'src': base + 'image_1920?unique=%s' % stamp,
                    'thumb': base + 'image_512?unique=%s' % stamp,
                    'alt': record.name or '',
                })
            for image in record.image_ids.filtered('id'):
                stamp = int(image.write_date.timestamp()) if image.write_date else 0
                base = '/web/image/coop.resource.image/%s/' % image.id
                images.append({
                    'id': image.id,
                    'src': base + 'image_1920?unique=%s' % stamp,
                    'thumb': base + 'image_256?unique=%s' % stamp,
                    'alt': image.name or record.name or '',
                })
            record.gallery_data = images
