# -*- coding: utf-8 -*-
"""Фото и видео записи — две карусели на витрине.

Владелец 12.11.2026 (задача 424): «везде, где у записи есть
изображения, — две карусели: фото и видео; добавлять при создании и
правке; пусто — без карусели, заглушка; в конце ленты „+“».

Решение 654: видео — файлом (вложение) или ссылкой (YouTube, VK,
Rutube, прямая ссылка на файл).

Одна модель на все разделы, привязка — парой `res_model` + `res_id`, как
у вложений: двенадцати разделам не нужно по своей таблице снимков.
Главный снимок остаётся `image_1920` самой записи — он же на карточке
каталога; здесь всё остальное.
"""
import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Ссылка на видео → адрес встраиваемого плеера.
_EMBEDS = (
    (re.compile(r'(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)'
                r'(?P<id>[\w-]{6,})'),
     'https://www.youtube.com/embed/{id}'),
    (re.compile(r'rutube\.ru/(?:video|play/embed|shorts)/(?P<id>[0-9a-f]{20,})'),
     'https://rutube.ru/play/embed/{id}'),
    (re.compile(r'(?:vk\.com|vkvideo\.ru)/(?:.*?)video(?P<oid>-?\d+)_(?P<vid>\d+)'),
     'https://vk.com/video_ext.php?oid={oid}&id={vid}&hd=2'),
)
_DIRECT = re.compile(r'^https?://\S+\.(?:mp4|webm|ogg|mov)(?:\?\S*)?$', re.I)

VIDEO_MAX_MB = 50


def video_embed(url):
    """Адрес плеера для ссылки и вид ('embed' | 'file') или (False, False)."""
    url = (url or '').strip()
    for pattern, template in _EMBEDS:
        match = pattern.search(url)
        if match:
            return template.format(**match.groupdict()), 'embed'
    if _DIRECT.match(url):
        return url, 'file'
    return False, False


class CoopMedia(models.Model):
    _name = 'coop.media'
    _description = 'Фото или видео записи'
    _order = 'sequence, id'

    res_model = fields.Char(string='Раздел', required=True, index=True)
    res_id = fields.Many2oneReference(
        string='Запись', model_field='res_model', required=True, index=True)
    kind = fields.Selection(
        [('photo', 'Фото'), ('video', 'Видео')],
        string='Что это', required=True, default='photo')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Подпись')

    image_1920 = fields.Image(string='Снимок', max_width=1920, max_height=1920)
    image_256 = fields.Image(related='image_1920', max_width=256,
                             max_height=256, store=True)

    video_file = fields.Binary(string='Файл видео', attachment=True)
    video_mimetype = fields.Char(string='Тип файла')
    video_url = fields.Char(string='Ссылка на видео')

    MAX_PER_RECORD = {'photo': 12, 'video': 8}

    @api.constrains('kind', 'image_1920', 'video_file', 'video_url')
    def _check_content(self):
        for media in self:
            if media.kind == 'photo' and not media.image_1920:
                raise ValidationError('У фото нет снимка.')
            if media.kind == 'video':
                if not media.video_file and not media.video_url:
                    raise ValidationError('У видео нет ни файла, ни ссылки.')
                if media.video_url and not video_embed(media.video_url)[0]:
                    raise ValidationError(
                        'Такую ссылку не показать: подойдут YouTube, VK, '
                        'Rutube или прямая ссылка на файл .mp4 / .webm.')

    @api.constrains('res_model', 'res_id', 'kind')
    def _check_limit(self):
        for media in self:
            count = self.search_count([
                ('res_model', '=', media.res_model),
                ('res_id', '=', media.res_id), ('kind', '=', media.kind)])
            limit = self.MAX_PER_RECORD[media.kind]
            if count > limit:
                raise ValidationError(
                    'К записи — не больше %s %s.' % (
                        limit, 'фото' if media.kind == 'photo' else 'видео'))

    # Править фото и видео может тот, кто может править саму запись: права
    # берём у движка, а не выводим заново (как `coop_can_edit`).
    def _check_parent_write(self):
        for media in self:
            if not media.res_model or media.res_model not in self.env:
                raise UserError('Неизвестный раздел записи.')
            self.env[media.res_model].browse(media.res_id).check_access('write')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_parent_write()
        return records

    def write(self, vals):
        self._check_parent_write()
        result = super().write(vals)
        if {'res_model', 'res_id'} & set(vals):
            self._check_parent_write()
        return result

    def unlink(self):
        self._check_parent_write()
        return super().unlink()

    def _coop_item(self):
        """Строка для виджета карусели."""
        self.ensure_one()
        stamp = int(self.write_date.timestamp()) if self.write_date else 0
        base = '/web/image/coop.media/%s/' % self.id
        if self.kind == 'photo':
            return {
                'id': 'm%s' % self.id, 'media_id': self.id,
                'src': base + 'image_1920?unique=%s' % stamp,
                'thumb': base + 'image_256?unique=%s' % stamp,
                'alt': self.name or '',
            }
        if self.video_url:
            src, how = video_embed(self.video_url)
        else:
            src = '/web/content/coop.media/%s/video_file?unique=%s' % (self.id, stamp)
            how = 'file'
        # Кадр для ленты: у файла его берёт сам браузер из ролика, у
        # YouTube — готовая картинка по номеру ролика. Rutube и VK
        # статичного кадра по ссылке не дают — там тёмная плитка.
        youtube = re.search(r'youtube\.com/embed/([\w-]+)', src or '')
        return {
            'id': 'm%s' % self.id, 'media_id': self.id,
            'src': src, 'how': how, 'mimetype': self.video_mimetype or '',
            'poster': 'https://i.ytimg.com/vi/%s/hqdefault.jpg' % youtube.group(1) if youtube else '',
            'alt': self.name or '',
        }


class CoopMediaMixin(models.AbstractModel):
    """Две карусели на витрине записи: фото и видео (`coop_media`)."""
    _name = 'coop.media.mixin'
    _description = 'Фото и видео записи'

    coop_media_data = fields.Json(
        string='Фото и видео', compute='_compute_coop_media_data')

    @api.depends_context('uid')
    def _compute_coop_media_data(self):
        Media = self.env['coop.media'].sudo()
        ids = [r.id for r in self if isinstance(r.id, int)]
        by_record = {}
        if ids:
            for media in Media.search([('res_model', '=', self._name),
                                       ('res_id', 'in', ids)]):
                by_record.setdefault(media.res_id, []).append(media)
        for record in self:
            items = by_record.get(record.id, []) if isinstance(record.id, int) else []
            photos = record._coop_media_photos()
            photos += [m._coop_item() for m in items if m.kind == 'photo']
            videos = [m._coop_item() for m in items if m.kind == 'video']
            record.coop_media_data = {
                'photos': photos,
                'videos': videos,
                'can_add': record._coop_media_can_add(),
                'limits': dict(Media.MAX_PER_RECORD),
                'video_mb': VIDEO_MAX_MB,
            }

    def _coop_media_can_add(self):
        self.ensure_one()
        if isinstance(self.id, int):
            return self.has_access('write')
        return self.browse().has_access('create')

    def _coop_media_photos(self):
        """Главный снимок записи — первым. Разделы со своей лентой
        снимков (объявления ресурсов) дописывают её сюда."""
        self.ensure_one()
        if 'image_1920' not in self._fields or not self.image_1920 \
                or not isinstance(self.id, int):
            return []
        stamp = int(self.write_date.timestamp()) if self.write_date else 0
        base = '/web/image/%s/%s/' % (self._name, self.id)
        return [{
            'id': 'main', 'main': True,
            'src': base + 'image_1920?unique=%s' % stamp,
            'thumb': base + 'image_512?unique=%s' % stamp
            if 'image_512' in self._fields else base + 'image_1920?unique=%s' % stamp,
            'alt': self.display_name or '',
        }]

    def coop_media_add(self, kind, data=None, url=None, name=None, mimetype=None):
        """Добавить фото или видео с витрины (кнопка «+»).

        Фото к записи без главного снимка становится главным — его видно и
        на карточке каталога.
        """
        self.ensure_one()
        self.check_access('write')
        if kind == 'photo':
            if not data:
                raise UserError('Нет снимка.')
            if 'image_1920' in self._fields and not self.image_1920:
                self.image_1920 = data
                return True
            return self._coop_media_add_photo(data, name)
        if kind == 'video':
            if url:
                if not video_embed(url)[0]:
                    raise UserError(
                        'Такую ссылку не показать: подойдут YouTube, VK, '
                        'Rutube или прямая ссылка на файл .mp4 / .webm.')
                vals = {'video_url': url.strip()}
            elif data:
                if len(data) * 3 / 4 > VIDEO_MAX_MB * 1024 * 1024:
                    raise UserError('Файл видео — не больше %s МБ.' % VIDEO_MAX_MB)
                vals = {'video_file': data, 'video_mimetype': mimetype or 'video/mp4'}
            else:
                raise UserError('Нет ни файла, ни ссылки.')
            self.env['coop.media'].create(dict(
                vals, res_model=self._name, res_id=self.id, kind='video',
                name=name or False, sequence=self._coop_media_next_seq('video')))
            return True
        raise UserError('Неизвестный вид: %s' % kind)

    def _coop_media_add_photo(self, data, name=None):
        self.env['coop.media'].create({
            'res_model': self._name, 'res_id': self.id, 'kind': 'photo',
            'image_1920': data, 'name': name or False,
            'sequence': self._coop_media_next_seq('photo'),
        })
        return True

    def _coop_media_next_seq(self, kind):
        last = self.env['coop.media'].sudo().search([
            ('res_model', '=', self._name), ('res_id', '=', self.id),
            ('kind', '=', kind)], order='sequence desc', limit=1)
        return (last.sequence or 0) + 1

    def unlink(self):
        media = self.env['coop.media'].sudo().search([
            ('res_model', '=', self._name), ('res_id', 'in', self.ids)])
        result = super().unlink()
        media.unlink()
        return result
