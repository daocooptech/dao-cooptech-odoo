# -*- coding: utf-8 -*-
"""Снимок по названию — один набор правил на все каталоги.

Правила подбора живут в загрузчике ресурсов: там их восемьдесят с
лишним, они выверены по названиям и порядок в них значим. Заводить
второй такой список для сделок, складчины и аукционов значило бы
получить два набора, которые разойдутся при первой же правке, — и
«Цемент М500» в одном каталоге был бы с мешками, а в другом с
экскаватором.

Поэтому здесь не правила, а доступ к ним: чем бы ни была запись, снимок
ей подбирается по тому же признаку, что и объявлению о ресурсе, — по
названию.
"""
import base64
import os
import re
import zlib

from . import load_resources

PHOTO_DIR = load_resources.PHOTO_DIR


def _variants(file):
    """Все снимки того же предмета: `wood-planks.jpg` и рядом
    `wood-planks-2.jpg`, `-3.jpg` и далее.

    Правило подбора одно на предмет, а записей с этим предметом в
    каталогах сотня: без разбора вариантов сто карточек получают один и
    тот же снимок. Владелец 15 сентября 2026: «одни и те же картинки
    везде, сделай все разные».

    Список читается с диска один раз и запоминается: он не меняется,
    пока идёт наполнение.
    """
    if file in _CACHE:
        return _CACHE[file]
    base = os.path.splitext(file)[0]
    # Читаем каталог, а не перебираем номера подряд: негодные снимки
    # удаляются вручную после просмотра, и в нумерации остаются дыры —
    # перебор обрывался бы на первой.
    sample = re.compile(r'^%s(-\d+)?\.jpg$' % re.escape(base))
    found_list = sorted(name for name in os.listdir(PHOTO_DIR)
                     if sample.match(name))
    _CACHE[file] = found_list
    return _CACHE[file]
    base = os.path.splitext(file)[0]
    found_list = [file] if os.path.exists(os.path.join(PHOTO_DIR, file)) else []
    n = 2
    while True:
        next_one = '%s-%s.jpg' % (base, n)
        if not os.path.exists(os.path.join(PHOTO_DIR, next_one)):
            break
        found_list.append(next_one)
        n += 1
    _CACHE[file] = found_list
    return found_list


_CACHE = {}


def photo_for(name):
    """Двоичное содержимое снимка по названию записи, или пусто.

    Возвращает готовое к записи в поле `Image` значение: Odoo ждёт
    base64, а не путь.
    """
    rule = load_resources._photo_by_name(name or '')
    if not rule:
        return None
    options = _variants(rule)
    if not options:
        return None
    # Выбор по названию, а не наугад: у одной и той же записи снимок
    # должен быть один и тот же при каждом прогоне наполнения, иначе
    # каталог меняется на ровном месте и отличить правку от шума нельзя.
    number = zlib.crc32((name or '').encode('utf-8')) % len(options)
    path = os.path.join(PHOTO_DIR, options[number])
    with open(path, 'rb') as fh:
        return base64.b64encode(fh.read())


def fill(records, field='image_1920', name_field='name'):
    """Проставить снимки там, где их нет.

    Идёт по записям, у которых поле снимка пусто, и ставит подобранный
    по названию. Возвращает, скольким поставили, — чтобы загрузчик мог
    об этом сказать в журнале, а не молчать.

    Пишет по одной записи: снимки разные, общего `write` тут не выйдет.
    """
    placed = 0
    for record in records:
        if record[field]:
            continue
        photo = photo_for(record[name_field])
        if not photo:
            continue
        record.sudo().write({field: photo})
        placed += 1
    return placed
