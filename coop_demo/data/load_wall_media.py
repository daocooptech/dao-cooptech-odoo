# -*- coding: utf-8 -*-
"""Записи с вложениями на стене главного участника витрины.

Владелец 24 сентября 2026: «добавь разного вида контент на стену и чтобы
это красиво смотрелось, например видео, аудиозапись или документ».

Четыре записи — по записи на вид вложения:

* видео — сварка полуавтоматом (`media/svarka.webm`);
* звук — голосовое: ровно работающий насос после замены двигателя
  (`media/nasos.ogg`). Помечается голосовым (`discuss.voice.metadata`),
  и движок показывает его своим проигрывателем с волной;
* документ — прайс на электромонтаж (`media/prays-elektromontazh.pdf`,
  собран здесь же, reportlab);
* фото — собранный щит и сварка каркаса (снимки из дизайн-макета).

Откуда файлы (владелец разрешил брать из сети для демо):

* `svarka.webm` — «MIG welding.webm», Wikimedia Commons, CC BY 3.0;
  источник назван в тексте записи, как того требует лицензия;
* `nasos.ogg` — «Pump.ogg», Wikimedia Commons, общественное достояние.

Повторный запуск ничего не удваивает: запись с тем же вложением на
стене уже есть — пропускается.
"""
import base64
import logging
import os
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

HERE = os.path.join(os.path.dirname(__file__), 'media')

POSTS = [
    {
        'days': 2,
        'body': 'Сварка полуавтоматом: показываю, как веду шов на каркасе '
                'под щит. Видео — Wikimedia Commons, CC BY 3.0.',
        'files': [('svarka.webm', 'Сварка полуавтоматом.webm', 'video/webm')],
    },
    {
        'days': 5,
        'body': 'Так звучит насос после замены двигателя — ровно, без стука '
                'и гула.',
        'files': [('nasos.ogg', 'Насос после замены двигателя.ogg', 'audio/ogg')],
        'voice': True,
    },
    {
        'days': 9,
        'body': 'Прайс на электромонтаж обновлён — во вложении. Выезд по '
                'Сочи бесплатно.',
        'files': [('prays-elektromontazh.pdf', 'Прайс на электромонтаж.pdf',
                   'application/pdf')],
    },
    {
        'days': 14,
        'body': 'Собранный щит на объекте и сварка каркаса под него.',
        'files': [('elektroshchit.jpg', 'Щит на объекте.jpg', 'image/jpeg'),
                  ('svarka-foto.jpg', 'Сварка каркаса.jpg', 'image/jpeg')],
    },
]


def load_wall_media(env, login='dashkevich'):
    page = env['res.users'].sudo().search(
        [('login', '=', login)], limit=1).partner_id
    if not page:
        return 0
    Attachment = env['ir.attachment'].sudo()
    Message = env['mail.message'].sudo()
    comment = env.ref('mail.mt_comment')
    Voice = env['discuss.voice.metadata'].sudo() \
        if 'discuss.voice.metadata' in env else None
    now = datetime.now()
    built = 0
    for post in sorted(POSTS, key=lambda p: -p['days']):
        names = [name for _src, name, _mime in post['files']]
        if Attachment.search_count([
                ('res_model', '=', 'res.partner'), ('res_id', '=', page.id),
                ('name', 'in', names)]):
            continue
        attachments = Attachment
        for src, name, mime in post['files']:
            with open(os.path.join(HERE, src), 'rb') as handle:
                data = handle.read()
            attachments |= Attachment.create({
                'name': name,
                'datas': base64.b64encode(data),
                'mimetype': mime,
                'res_model': 'res.partner',
                'res_id': page.id,
            })
        if post.get('voice') and Voice is not None:
            for attachment in attachments:
                Voice.create({'attachment_id': attachment.id})
        Message.create({
            'model': 'res.partner',
            'res_id': page.id,
            'message_type': 'comment',
            'subtype_id': comment.id,
            'author_id': page.id,
            'body': '<p>%s</p>' % post['body'],
            'date': now - timedelta(days=post['days']),
            'attachment_ids': [(6, 0, attachments.ids)],
        })
        built += 1
    _logger.info('Стена витрины: записей с вложениями %s', built)
    return built
