# -*- coding: utf-8 -*-
"""Видео в карусели витрин (задача 424, решение 654).

Видео — тот же ролик, что на стене (`media/svarka.webm`, «MIG
welding.webm», Wikimedia Commons, CC BY 3.0; источник — в подписи).
Вешается только к записям, где сварка к месту: по словам в названии.
У остальных видео нет — витрина показывает заглушку, как и задумано.

Хранилище не раздувается: движок кладёт одинаковые файлы один раз (по
контрольной сумме). Идемпотентно: запись, у которой видео уже есть,
пропускается.
"""
import base64
import logging
import os

_logger = logging.getLogger(__name__)

HERE = os.path.join(os.path.dirname(__file__), 'media')
FILE = 'svarka.webm'
CAPTION = 'Сварка полуавтоматом — Wikimedia Commons, CC BY 3.0'
WORDS = ('свар', 'металл', 'каркас', 'металлоконструк', 'электромонтаж', 'ангар')
MODELS = ('coop.resource', 'coop.project', 'coop.vacancy', 'coop.skill.offer',
          'coop.barter.offer', 'coop.bounty', 'coop.community', 'coop.event',
          'coop.groupbuy', 'coop.intangible', 'coop.mining.offer', 'coop.program')


def load_media_video(env):
    with open(os.path.join(HERE, FILE), 'rb') as fh:
        data = base64.b64encode(fh.read()).decode()
    Media = env['coop.media'].sudo()
    created = 0
    for model in MODELS:
        if model not in env:
            continue
        domain = ['|'] * (len(WORDS) - 1) + [('name', 'ilike', w) for w in WORDS]
        records = env[model].sudo().with_context(active_test=False).search(domain, order='id')
        have = set(Media.search([('res_model', '=', model), ('kind', '=', 'video'),
                                 ('res_id', 'in', records.ids)]).mapped('res_id'))
        # По одной и со сбросом кэша: пачкой 39 копий ролика (4,4 МБ)
        # боевая выкатка 12.11 упала с MemoryError — у процесса
        # обновления лимит памяти ~780 МБ.
        for record in records:
            if record.id in have:
                continue
            Media.create({'res_model': model, 'res_id': record.id, 'kind': 'video',
                          'video_file': data, 'video_mimetype': 'video/webm',
                          'name': CAPTION, 'sequence': 1})
            env.flush_all()
            env.invalidate_all()
            created += 1
    _logger.info('Видео в карусели витрин: добавлено %s', created)
    return created
