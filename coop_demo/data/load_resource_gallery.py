# -*- coding: utf-8 -*-
"""Ещё снимки к объявлениям ресурсов — лента под главным снимком.

Владелец 10.11.2026: «под главным фото сделай снизу слайдер из маленьких
фото 2–5». Снимки — из того же набора, что главный (`static/img/
resources`): файлы одной темы названы `тема-N.jpg`, и к объявлению
берутся соседи его главного снимка по теме. Сколько — от одного до
четырёх, по номеру объявления: у части ленты нет вовсе (один снимок),
чтобы каталог не выглядел отштампованным.

Хранилище не раздувается: движок кладёт одинаковые файлы один раз (по
контрольной сумме), а тем всего несколько десятков.

Идемпотентно: объявления, у которых снимки уже есть, не трогаются.
"""
import base64
import hashlib
import logging
import os
import re

from odoo.addons.coop_demo.data.load_resources import PHOTO_DIR

_logger = logging.getLogger(__name__)

THEME = re.compile(r'^(?P<theme>.+?)-(?P<num>\d+)\.(jpe?g|png|webp)$', re.I)


def _themes():
    """Тема снимка → файлы темы по порядку номера."""
    themes = {}
    for file in sorted(os.listdir(PHOTO_DIR)):
        match = THEME.match(file)
        if match:
            themes.setdefault(match['theme'], []).append((int(match['num']), file))
    return {theme: [f for _n, f in sorted(files)] for theme, files in themes.items()}


def load_resource_gallery(env):
    themes = _themes()
    # Главный снимок узнаём по содержимому: имя файла объявление не
    # хранит, а контрольная сумма вложения совпадает с суммой файла.
    by_checksum = {}
    for files in themes.values():
        for file in files:
            with open(os.path.join(PHOTO_DIR, file), 'rb') as fh:
                by_checksum[hashlib.sha1(fh.read()).hexdigest()] = file
    file_theme = {f: t for t, files in themes.items() for f in files}

    Attachment = env['ir.attachment'].sudo()
    Image = env['coop.resource.image'].sudo()
    resources = env['coop.resource'].sudo().with_context(active_test=False).search(
        [('image_ids', '=', False)], order='id')
    cache = {}
    created = skipped = 0
    for resource in resources:
        attachment = Attachment.search([
            ('res_model', '=', 'coop.resource'), ('res_id', '=', resource.id),
            ('res_field', '=', 'image_1920')], limit=1)
        main = by_checksum.get(attachment.checksum) if attachment else None
        theme = file_theme.get(main)
        if not theme:
            skipped += 1
            continue
        others = [f for f in themes[theme] if f != main]
        # 0–4 дополнительных снимка: у каждого пятого ленты нет.
        want = min(len(others), resource.id % 5)
        if not want:
            continue
        start = resource.id % len(others)
        picked = [others[(start + i) % len(others)] for i in range(want)]
        vals = []
        for seq, file in enumerate(picked, 1):
            if file not in cache:
                with open(os.path.join(PHOTO_DIR, file), 'rb') as fh:
                    cache[file] = base64.b64encode(fh.read()).decode()
            vals.append({'resource_id': resource.id, 'sequence': seq,
                         'image_1920': cache[file]})
        Image.create(vals)
        created += len(vals)
    _logger.info('Лента снимков ресурсов: добавлено %s, без темы главного снимка %s',
                 created, skipped)
    return created
