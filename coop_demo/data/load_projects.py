# -*- coding: utf-8 -*-
"""Каталог проектов (краудресурсинг) из макета — и добор сверх него.

Сто проектов взяты из `projects.html`. Готовность в макете записана
числом, но по устройству раздела она не вводится, а считается: собрано
против нужного. Поэтому число из макета используется наоборот — из него
и суммы «нужно» восстанавливаются вклады, которые и попадают в базу.
Дальше готовность считается сама и меняется, когда в проект вносят
что-то ещё.

Сверх макета дописываются проекты, чтобы опубликованных было больше ста
даже после того, как часть уйдёт в черновики по нехватке верификации у
инициатора (решение владельца от 2026-09-02).
"""
import base64
import io
import json
import logging
import os
import random

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
PHOTO_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img', 'projects')

KIND = {
    'Кооперативный': 'cooperative',
    'Коммерческий': 'commercial',
    'Некоммерческий': 'nonprofit',
    'ДАО': 'dao',
}

# Чем скидываются. Доли подобраны так, чтобы в каталоге было видно главное
# отличие краудресурсинга: деньги — не большинство вкладов.
CONTRIBUTION_KINDS = [
    ('money', 'Денежный взнос'),
    ('labour', 'Работы по проекту'),
    ('labour', 'Смены на площадке'),
    ('resource', 'Техника на время работ'),
    ('material', 'Материалы'),
    ('space', 'Помещение под работы'),
    ('knowledge', 'Проект и расчёты'),
]

# Порядок сумм «нужно» — от небольшой инициативы до серьёзной стройки.
REQUIRED_STEPS = [180000, 340000, 620000, 900000, 1450000, 2400000,
                  3800000, 5200000, 8500000, 12000000]


def load_projects(env, extra=45):
    with io.open(os.path.join(HERE, 'projects.json'), encoding='utf-8') as fh:
        rows = json.load(fh)

    Project = env['coop.project'].sudo()
    Category = env['coop.project.category'].sudo()
    Contribution = env['coop.project.contribution'].sudo()
    Partner = env['res.partner'].sudo()

    categories = _load_categories(Category, rows)
    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)], order='id')
    companies = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)], order='id')
    initiators = list(companies) + list(people)
    if not initiators:
        _logger.warning('Нет участников — каталог проектов не наполняю')
        return

    rnd = random.Random(20260902)
    created = updated = 0

    for index, row in enumerate(rows + _extra_rows(rows, extra, rnd)):
        key = 'projects.json#%s' % index
        initiator = initiators[(index * 5) % len(initiators)]
        required = REQUIRED_STEPS[index % len(REQUIRED_STEPS)]
        readiness = max(1, min(100, int(row['readiness'])))

        values = {
            'name': row['name'],
            'summary': row['description'],
            'description': '<p>%s</p>' % row['description'] if row['description'] else False,
            'city': row['city'],
            'kind': KIND.get(row['project_type'], 'cooperative'),
            'category_id': categories.get(row['category'], {}).get('id'),
            'subcategory_id': categories.get(row['category'], {}).get(
                'children', {}).get(row['subcategory']),
            'partner_id': initiator.id,
            'author_id': (initiator if not initiator.is_company
                          else people[index % len(people)]).id,
            'required_total': required,
            'import_key': key,
        }
        photo = os.path.join(PHOTO_DIR, os.path.basename(row['photo'])) if row['photo'] else ''
        if photo and os.path.exists(photo):
            with open(photo, 'rb') as fh:
                values['image_1920'] = base64.b64encode(fh.read())

        project = Project.search([('import_key', '=', key)], limit=1)
        if project:
            project.write(values)
            updated += 1
        else:
            project = Project.create(values)
            created += 1

        if not project.contribution_ids:
            _make_contributions(Contribution, project, required, readiness,
                               people, rnd, index)
        project.state = _state_for(project.readiness, index)

    _logger.info('Каталог проектов: создано %s, обновлено %s', created, updated)


def _load_categories(Category, rows):
    """Темы и разделы — из самого макета, а не отдельным справочником.

    Держать их списком в коде значит завести второй источник правды: в
    макете тему поправят, а здесь забудут.
    """
    tree = {}
    for row in rows:
        tree.setdefault(row['category'], set())
        if row['subcategory']:
            tree[row['category']].add(row['subcategory'])

    result = {}
    for name, children in tree.items():
        parent = Category.search(
            [('name', '=', name), ('parent_id', '=', False)], limit=1)
        if not parent:
            parent = Category.create({'name': name})
        entry = {'id': parent.id, 'children': {}}
        for child_name in sorted(children):
            child = Category.search(
                [('name', '=', child_name), ('parent_id', '=', parent.id)], limit=1)
            if not child:
                child = Category.create({'name': child_name, 'parent_id': parent.id})
            entry['children'][child_name] = child.id
        result[name] = entry
    return result


def _make_contributions(Contribution, project, required, readiness, people, rnd, index):
    """Восстановить вклады из готовности, а не выставить готовность руками.

    Готовность — следствие: собрано против нужного. Чтобы в каталоге она
    совпала с макетом, из неё восстанавливается собранная сумма, а та
    раскладывается на несколько вкладов разного рода.
    """
    collected = round(required * readiness / 100.0)
    parts = rnd.choice([2, 3, 3, 4, 4, 5, 6])
    # Первый вклад крупнее прочих: так обычно и бывает — кто-то вносит
    # основное, остальные добавляют.
    weights = [3.0] + [rnd.uniform(0.6, 1.6) for _ in range(parts - 1)]
    total_weight = sum(weights)

    for offset, weight in enumerate(weights):
        kind, title = CONTRIBUTION_KINDS[(index + offset) % len(CONTRIBUTION_KINDS)]
        value = round(collected * weight / total_weight)
        if value <= 0:
            continue
        contributor = people[(index * 3 + offset * 11) % len(people)]
        Contribution.create({
            'project_id': project.id,
            'partner_id': contributor.id,
            'kind': kind,
            'name': title,
            'value': value,
            'state': 'accepted',
            'offered_on': '20%02d-%02d-%02d' % (
                23 + (index % 3), 1 + (offset % 12), 1 + ((index + offset) % 27)),
            'accepted_on': '20%02d-%02d-%02d' % (
                23 + (index % 3), 1 + (offset % 12), 2 + ((index + offset) % 26)),
        })

    # Один непринятый вклад у части проектов: экран «предложен» должен
    # быть на чём проверить, и разговор о цене вклада — обычное дело.
    if index % 6 == 2:
        Contribution.create({
            'project_id': project.id,
            'partner_id': people[(index * 7) % len(people)].id,
            'kind': 'resource',
            'name': 'Техника на время работ',
            'value': round(required * 0.08),
            'state': 'offered',
        })


def _state_for(readiness, index):
    """Состояние по готовности, с разбросом.

    Замыслы и отменённые нужны, чтобы соответствующие экраны было на чём
    проверить; их доли небольшие — каталог должен оставаться каталогом.
    """
    if index % 29 == 7:
        return 'draft'
    if index % 37 == 11:
        return 'cancelled'
    if readiness >= 100:
        return 'done' if index % 3 == 0 else 'running'
    return 'gathering'


def _extra_rows(rows, extra, rnd):
    """Дописать проектов сверх макета.

    Решение владельца: опубликованных должно быть больше ста. После
    того как часть уйдёт в черновики по нехватке верификации у
    инициатора, ста из ста не остаётся — значит записей нужно больше.

    Названия собираются из тех же тем и городов, что в макете, а не
    нумерацией: «Проект №117» — это не пример, а заполнитель.
    """
    prefixes = [
        'Общая мастерская', 'Кооперативный склад', 'Солнечная станция',
        'Пункт приёма вторсырья', 'Школа ремёсел', 'Сушильный цех',
        'Молочная кухня', 'Ремонтная база', 'Питомник саженцев',
        'Пекарня полного цикла', 'Пасека на паях', 'Овощехранилище',
        'Швейный цех', 'Медиацентр посёлка', 'Пункт проката техники',
    ]
    cities = sorted({row['city'] for row in rows})
    extras = []
    for i in range(extra):
        source = rows[(i * 7) % len(rows)]
        city = cities[(i * 3) % len(cities)]
        extras.append({
            'name': '%s — %s' % (prefixes[i % len(prefixes)], city),
            'description': source['description'],
            'city': city,
            'category': source['category'],
            'subcategory': source['subcategory'],
            'project_type': source['project_type'],
            # Каждый седьмой собран полностью: иначе запуск проекта и
            # передачу его в модуль управления проверить не на чем —
            # в макете готовность нигде не доходит до ста.
            'readiness': 100 if i % 7 == 3 else rnd.randint(8, 99),
            'photo': source['photo'],
        })
    return extras
