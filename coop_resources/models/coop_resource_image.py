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
    _inherit = ['coop.resource', 'coop.media.mixin']

    image_ids = fields.One2many(
        'coop.resource.image', 'resource_id', string='Ещё снимки',
        help='Показываются лентой под главным снимком.')
    image_count = fields.Integer(
        string='Снимков', compute='_compute_image_count')

    @api.depends('image_1920', 'image_ids')
    def _compute_image_count(self):
        for record in self:
            record.image_count = (1 if record.image_1920 else 0) + len(record.image_ids)

    # Своя лента снимков объявления — в общей карусели фото
    # (`coop_media`, задача 424) сразу за главным снимком.
    def _coop_media_photos(self):
        photos = super()._coop_media_photos()
        for image in self.image_ids.filtered('id') if isinstance(self.id, int) else []:
            stamp = int(image.write_date.timestamp()) if image.write_date else 0
            base = '/web/image/coop.resource.image/%s/' % image.id
            photos.append({
                'id': 'r%s' % image.id,
                'src': base + 'image_1920?unique=%s' % stamp,
                'thumb': base + 'image_256?unique=%s' % stamp,
                'alt': image.name or self.name or '',
            })
        return photos

    def _coop_media_add_photo(self, data, name=None):
        last = self.image_ids[-1:]
        self.env['coop.resource.image'].create({
            'resource_id': self.id, 'image_1920': data, 'name': name or False,
            'sequence': (last.sequence or 0) + 1,
        })
        return True
