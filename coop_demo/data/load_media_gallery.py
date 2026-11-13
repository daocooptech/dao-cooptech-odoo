# -*- coding: utf-8 -*-
"""Ленты фото под главным снимком — во всех каталогах (задача 444).

Владелец 13.11.2026: «почему нигде нет слайдеров с фото и видео?
заполни везде где можно». Слайдер (`coop_media`, задача 424) стоял на
формах, но у записей был один главный снимок: без второго нет ни ленты,
ни стрелок, и витрина выглядела картинкой, а не слайдером.

Каждой демо-записи — от трёх до шести снимков вместе с главным и видео
(сколько — по записи, чтобы каталог не выглядел отштампованным). Снимки
из локального набора `static/img` (внешних ссылок в демо нет), подбор:

1. тот же предмет, что на главном снимке (узнаётся по контрольной
   сумме вложения — она совпадает с суммой файла);
2. все правила подбора по названию (`load_resources.PHOTO_RULES`), а не
   только первое — у «Пасеки и сыроварни» и пчёлы, и сыр;
3. запасные предметы раздела (склад — стеллажи и холодильные камеры,
   событие — сбор людей), если первых двух мало.

Разные записи с одним предметом начинают ленту с разных снимков (сдвиг
по номеру записи), снимки в ленте не повторяются.

Только записи наполнения (`create_uid` = суперпользователь): объявлениям
живых людей чужие снимки не подкладываются. Идемпотентно: запись, у
которой снимков уже сколько нужно, пропускается. Пишет пачками со
сбросом кэша — у процесса обновления на боевой лимит памяти.
"""
import base64
import hashlib
import logging
import os
import re
import zlib

from odoo import SUPERUSER_ID

from . import load_resources

_logger = logging.getLogger(__name__)

IMG = os.path.dirname(load_resources.PHOTO_DIR)
DIRS = ('resources', 'projects', 'skills', 'vacancies')
SUBJECT = re.compile(r'^(?P<s>.+?)(?:-\d+)?\.(?:jpe?g|png|webp)$', re.I)
BATCH = 150

# Раздел → запасные предметы (имена файлов без номера).
FALLBACK = {
    'coop.resource': ('toolbox', 'warehouse-shelves', 'van-delivery'),
    'coop.project': ('building-renovation', 'community-gathering', 'workshop-class',
                     'carpentry-shop'),
    'coop.vacancy': ('business-meeting', 'office-desk', 'workshop-class',
                     'factory-operator'),
    'coop.skill.offer': ('workshop-class', 'laptop-desk', 'craft-workshop', 'toolbox'),
    'coop.barter.offer': ('shop-counter', 'plastic-crates', 'toolbox', 'central-market'),
    'coop.bounty.task': ('laptop-desk', 'office-desk', 'programmer', 'video-call'),
    'coop.community': ('community-gathering', 'assembly-hall', 'harvest-festival',
                       'volunteer-cleanup'),
    'coop.event': ('community-gathering', 'assembly-hall', 'harvest-festival',
                   'folk-dance', 'workshop-class'),
    'coop.groupbuy': ('plastic-crates', 'van-delivery', 'warehouse-shelves',
                      'central-market'),
    'coop.intangible': ('laptop-desk', 'office-desk', 'library-shelves', 'ui-design',
                        'programmer'),
    'coop.mining.offer': ('server-rack', 'network-switch', 'battery-inverter',
                          'solar-panels'),
    'coop.program': ('community-gathering', 'workshop-class', 'business-meeting',
                     'assembly-hall'),
    'coop.warehouse.offer': ('warehouse', 'warehouse-shelves', 'plastic-crates',
                             'cold-storage', 'grain-silo'),
    'coop.auction': ('central-market', 'shop-counter', 'toolbox'),
}
# Не каталоги: слайдер только в каталогах, у людей и организаций его нет
# (владелец 14.11). Снимки, разложенные им наполнением 13.11, — убрать.
NOT_CATALOG = ('res.partner',)
# Склады — по типу хранения, а не по названию «Аренда места на складе».
STORAGE = {
    'cold': ('cold-storage', 'milk-tank'),
    'freezer': ('cold-storage', 'beef-meat'),
    'grain': ('grain-silo', 'hay-bales', 'wheat-field'),
    'open': ('mobile-crane', 'brick-stack', 'timber-beam'),
    'dry_heated': ('warehouse-shelves', 'warehouse'),
    'dry_unheated': ('warehouse', 'garage-building'),
}


def _index():
    """Предмет → файлы (без повторов по содержимому); сумма → (предмет, файл)."""
    subjects, by_sum, seen = {}, {}, set()
    for folder in DIRS:
        path = os.path.join(IMG, folder)
        if not os.path.isdir(path):
            continue
        for name in sorted(os.listdir(path)):
            match = SUBJECT.match(name)
            if not match:
                continue
            full = os.path.join(path, name)
            with open(full, 'rb') as fh:
                digest = hashlib.sha1(fh.read()).hexdigest()
            by_sum[digest] = (match['s'], full)
            if digest in seen:
                continue
            seen.add(digest)
            subjects.setdefault(match['s'], []).append(full)
    return subjects, by_sum


def _rule_subjects(text):
    bottom = (text or '').lower()
    out = []
    for keys, file in load_resources.PHOTO_RULES:
        if file and any(key in bottom for key in keys):
            subject = SUBJECT.match(file)
            if subject and subject['s'] not in out:
                out.append(subject['s'])
    return out


def _want(model, rid):
    """Сколько всего медиа у записи: 3–6, всегда одинаково для неё."""
    return 3 + zlib.crc32(('%s:%s' % (model, rid)).encode()) % 4


def _models(env):
    names = [m for m in FALLBACK if m in env and 'coop_media_data' in env[m]._fields]
    return names


def _records(env, model):
    domain = [('create_uid', '=', SUPERUSER_ID)]
    return env[model].sudo().with_context(active_test=False).search(domain, order='id')


def load_media_gallery(env):
    subjects, by_sum = _index()
    Attachment = env['ir.attachment'].sudo()
    Media = env['coop.media'].sudo()
    stray = Media.search([('res_model', 'in', NOT_CATALOG), ('create_uid', '=', SUPERUSER_ID)])
    if stray:
        _logger.info('Ленты фото: убрано %s снимков не из каталогов', len(stray))
        stray.unlink()
    total = 0
    for model in _models(env):
        records = _records(env, model)
        ids = records.ids
        if not ids:
            continue
        resource = model == 'coop.resource' and 'coop.resource.image' in env
        # Сколько уже есть: доп. медиа + главный снимок.
        have = {}
        for rid, count in Media._read_group([('res_model', '=', model), ('res_id', 'in', ids)],
                                            ['res_id'], ['__count']):
            have[rid] = count
        if resource:
            for res, count in env['coop.resource.image'].sudo()._read_group(
                    [('resource_id', 'in', ids)], ['resource_id'], ['__count']):
                have[res.id] = have.get(res.id, 0) + count
        mains = {}
        field = 'image_512' if model == 'coop.auction' else 'image_1920'
        for att in Attachment.search_read([('res_model', '=', model), ('res_id', 'in', ids),
                                           ('res_field', '=', field)],
                                          ['res_id', 'checksum']):
            mains[att['res_id']] = att['checksum']
        todo = [rid for rid in ids if _want(model, rid) > have.get(rid, 0) + (1 if rid in mains else 0)]
        created = 0
        for start in range(0, len(todo), BATCH):
            chunk = env[model].sudo().with_context(active_test=False).browse(
                todo[start:start + BATCH])
            cache = {}
            media_vals, image_vals = [], []
            for record in chunk:
                main = by_sum.get(mains.get(record.id))
                order = []
                if main:
                    order.append(main[0])
                text = record.display_name or ''
                if model == 'coop.auction' and record.resource_id:
                    text += ' ' + record.resource_id.name
                for subject in _rule_subjects(text):
                    if subject not in order:
                        order.append(subject)
                if model == 'coop.warehouse.offer':
                    for subject in STORAGE.get(record.storage_kind, ()):
                        if subject not in order:
                            order.append(subject)
                for subject in FALLBACK[model]:
                    if subject not in order:
                        order.append(subject)
                shift = zlib.crc32(('%s:%s' % (model, record.id)).encode())
                picked = []
                need = _want(model, record.id) - have.get(record.id, 0) \
                    - (1 if record.id in mains else 0)
                for subject in order:
                    files = subjects.get(subject) or []
                    if not files:
                        continue
                    k = shift % len(files)
                    for path in files[k:] + files[:k]:
                        if main and path == main[1]:
                            continue
                        if path not in picked:
                            picked.append(path)
                            break   # по одному с предмета, потом по второму кругу
                    if len(picked) >= need:
                        break
                # Второй круг — если предметов меньше, чем нужно снимков.
                if len(picked) < need:
                    for subject in order:
                        for path in subjects.get(subject) or []:
                            if len(picked) >= need:
                                break
                            if path not in picked and not (main and path == main[1]):
                                picked.append(path)
                        if len(picked) >= need:
                            break
                for seq, path in enumerate(picked[:need], have.get(record.id, 0) + 2):
                    if path not in cache:
                        with open(path, 'rb') as fh:
                            cache[path] = base64.b64encode(fh.read()).decode()
                    if resource:
                        image_vals.append({'resource_id': record.id, 'sequence': seq,
                                           'image_1920': cache[path]})
                    else:
                        media_vals.append({'res_model': model, 'res_id': record.id,
                                           'kind': 'photo', 'sequence': seq,
                                           'image_1920': cache[path]})
            if image_vals:
                env['coop.resource.image'].sudo().create(image_vals)
            if media_vals:
                Media.create(media_vals)
            created += len(image_vals) + len(media_vals)
            env.flush_all()
            env.invalidate_all()
        if created:
            _logger.info('Ленты фото: %s — добавлено %s снимков к %s записям',
                         model, created, len(todo))
        total += created
    return total
