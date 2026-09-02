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

# Снимок к проекту подбирается по названию, а не берётся из выгрузки
# макета: там фотографии перемешаны — «Скалодром» иллюстрировался
# пекарней, «Ветряк» — пасекой. На плитке видны как раз снимок и
# описание, поэтому расхождение бросается в глаза первым.
# Названия повторяются (теплиц в выгрузке пять), и для каждого держится
# несколько кадров, чтобы каталог не выглядел размноженной карточкой.
PHOTOS_BY_NAME = {
    'Строительный 3д принтер': ['printer3d-arm.jpg'],
    'Круглогодичная теплица': ['greenhouse-interior.jpg', 'greenhouse-lettuce.jpg'],
    'Тепличный комбинат': ['greenhouse-lettuce.jpg', 'greenhouse-interior.jpg'],
    'Биовегетарий': ['greenhouse-lettuce.jpg'],
    'Раздельный сбор мусора': ['plastic-recycling.jpg'],
    'Пункт приёма вторсырья': ['recycling-plastic.jpg', 'plastic-recycling.jpg'],
    'Мастерская по переработке пластика': ['recycling-center.jpg'],
    'Цех переработки шерсти': ['sewing-workshop.jpg', 'weaving-loom.jpg'],
    'Антикафе «FabLab»': ['makerspace.jpg'],
    'Молодёжный технопарк': ['printer3d-arm.jpg', 'makerspace.jpg'],
    'Соседский коворкинг': ['coworking.jpg'],
    'Коворкинг в райцентре': ['coworking.jpg', 'office-desk.jpg', 'laptop-desk.jpg'],
    'Общественная прачечная': ['community-meeting.jpg'],
    'Общественная баня': ['building-renovation.jpg', 'community-meeting.jpg'],
    'Ремонт дома культуры': ['building-renovation.jpg'],
    'Реставрация исторического здания': ['historic-restoration.jpg'],
    'Сельский музей': ['historic-restoration.jpg', 'building-renovation.jpg'],
    'Модульные дома для многодетных семей': ['house-amie.jpg'],
    'Модульный дом из бруса': ['modular-house.jpg', 'house-serendix.jpg', 'house-tecla.jpg'],
    'Солнечная электростанция': ['solar-farm.jpg'],
    'Солнечная станция посёлка': ['solar-farm.jpg'],
    'Зарядная станция': ['diesel-generator.jpg', 'solar-farm.jpg'],
    'Ветропарк для малых хозяйств': ['wind-turbine.jpg'],
    'Ветряк на 25 кВт': ['wind-turbine.jpg'],
    'Ремонт моста через реку': ['bridge-repair.jpg'],
    'Ремонт моста': ['bridge-repair.jpg', 'pedestrian-bridge.jpg'],
    'Строительство моста-пешеходника': ['pedestrian-bridge.jpg'],
    'Детская игровая площадка': ['playground.jpg'],
    'Детская площадка': ['playground.jpg'],
    'Скалодром в бывшем цехе': ['climbing-gym.jpg'],
    'Кооперативная пекарня': ['bakery-bread.jpg'],
    'Пекарня полного цикла': ['bakery.jpg', 'bakery-bread.jpg'],
    'Мельница на паях': ['flour-mill.jpg', 'wheat-flour.jpg', 'grain-silo.jpg'],
    'Овощехранилище': ['warehouse-shelves.jpg'],
    'Сушильный комплекс': ['herb-drying.jpg', 'berry-harvest.jpg', 'apple-orchard.jpg'],
    'Сыроварня кооператива': ['cheese-making.jpg'],
    'Молочный цех': ['milk-tank.jpg', 'milk-bottles.jpg', 'cattle-barn.jpg'],
    'Рыбное хозяйство': ['poultry-house.jpg', 'goat-farm.jpg'],
    'Гончарная мастерская': ['craft-workshop.jpg'],
    'Кузнечная мастерская': ['craft-workshop.jpg', 'sawmill-logs.jpg'],
    'Ткацкая артель': ['weaving-loom.jpg', 'sewing-workshop.jpg'],
    'Мастерская по ремонту техники': ['bicycle-repair.jpg', 'carpentry-shop.jpg',
                                      'excavator-work.jpg'],
    'Библиотека инструментов': ['toolbox.jpg'],
    'Библиотека под открытым небом': ['outdoor-library.jpg'],
    'Мобильный медпункт для отдалённых сёл': ['mobile-clinic.jpg'],
    'Медпункт на селе': ['mobile-clinic.jpg'],
    'Школа программирования для подростков': ['programmer.jpg'],
    'Открытая CRM для кооперативов': ['open-source-crm.jpg'],
    'Ремонт дома культуры ': ['building-renovation.jpg'],
}


# Проекты сверх выгрузки макета. Решение владельца: опубликованных
# должно быть больше ста, а после ухода части в черновики по нехватке
# верификации ста из ста не остаётся. Название, описание и снимок здесь
# заданы вместе — если тянуть описание у случайной строки выгрузки,
# «Пасека на паях» получает текст про рассадный комплекс.
EXTRA_PROJECTS = [
    ('Общая мастерская', 'Малый бизнес и ремёсла',
     'Станки, верстаки и вытяжка в общем доступе: час работы '
     'оплачивается по счётчику, инструмент — из паевого фонда.',
     ['makerspace.jpg', 'craft-workshop.jpg']),
    ('Кооперативный склад', 'Малый бизнес и ремёсла',
     'Отапливаемый склад с погрузчиком: места разбирают пайщики, '
     'свободные ячейки уходят соседям по себестоимости.',
     ['warehouse-shelves.jpg']),
    ('Солнечная станция', 'Технологии и инновации',
     'Сто киловатт на крышах четырёх домов; излишки уходят в сеть, '
     'выручка делится по паям.',
     ['solar-farm.jpg']),
    ('Пункт приёма вторсырья', 'Экология и природа',
     'Приём картона, плёнки и ПЭТ шесть дней в неделю; прессованное '
     'сырьё вывозят переработчику раз в месяц.',
     ['recycling-plastic.jpg', 'plastic-recycling.jpg']),
    ('Школа ремёсел', 'Образование и наука',
     'Двухлетний курс по дереву, керамике и ткачеству; наставники — '
     'мастера с окрестных подворий.',
     ['craft-workshop.jpg', 'weaving-loom.jpg']),
    ('Сушильный цех', 'Сельское хозяйство и еда',
     'Конвейерные сушилки для ягод, грибов и трав: сезонный урожай '
     'перестаёт пропадать за неделю.',
     ['herb-drying.jpg', 'berry-harvest.jpg']),
    ('Молочная кухня', 'Сельское хозяйство и еда',
     'Пастеризация, розлив и творожная линия; сырьё принимают у шести '
     'подворий по договору.',
     ['milk-bottles.jpg', 'milk-tank.jpg']),
    ('Ремонтная база', 'Малый бизнес и ремёсла',
     'Ремонт мотоблоков, косилок и велосипедов: подъёмник, сварка и '
     'склад расходников на паях.',
     ['bicycle-repair.jpg', 'carpentry-shop.jpg']),
    ('Питомник саженцев', 'Сельское хозяйство и еда',
     'Районированные яблони, груши и ягодные кустарники; весной каждый '
     'пайщик забирает долю саженцами.',
     ['apple-orchard.jpg']),
    ('Пекарня полного цикла', 'Сельское хозяйство и еда',
     'Своя мельница, подовая печь и ночная смена: хлеб развозят по '
     'шести сёлам к завтраку.',
     ['bakery.jpg', 'bakery-bread.jpg', 'flour-mill.jpg']),
    ('Пасека на паях', 'Сельское хозяйство и еда',
     'Сорок ульев на общем точке; откачка и фасовка совместные, мёд '
     'делится по числу паёв.',
     ['apiary-hives.jpg']),
    ('Овощехранилище', 'Сельское хозяйство и еда',
     'Хранилище с регулируемой температурой: осенний урожай доживает '
     'до весенней цены, а не до помойки.',
     ['warehouse-shelves.jpg', 'grain-silo.jpg']),
    ('Швейный цех', 'Малый бизнес и ремёсла',
     'Пятнадцать машин, раскройный стол и оверлок; шьём спецодежду по '
     'заказам соседних кооперативов.',
     ['sewing-workshop.jpg']),
    ('Медиацентр посёлка', 'Культура и искусство',
     'Студия звука и видео в бывшем клубе: местные новости, записи '
     'концертов и занятия с подростками.',
     ['building-renovation.jpg', 'historic-restoration.jpg']),
    ('Пункт проката техники', 'Малый бизнес и ремёсла',
     'Мотоблоки, бетономешалки, леса и генератор в общем пользовании; '
     'залог и график — через платформу.',
     ['toolbox.jpg', 'excavator-work.jpg']),
    ('Зелёный двор', 'Экология и природа',
     'Двор без асфальта: дренаж, живая изгородь и компостная площадка '
     'на две многоэтажки.',
     ['apple-orchard.jpg', 'outdoor-library.jpg']),
    ('Спортивная площадка', 'Спорт и активный отдых',
     'Турники, зона воркаута и коробка с искусственным покрытием; '
     'зимой заливают каток.',
     ['playground.jpg', 'climbing-gym.jpg']),
    ('Фельдшерский пункт', 'Здоровье и медицина',
     'Кабинет приёма и процедурная в отремонтированном здании; '
     'фельдшер на ставке кооператива.',
     ['mobile-clinic.jpg']),
    ('Общественная библиотека', 'Культура и искусство',
     'Навес, полки и обмен книгами в парке — работает без '
     'библиотекаря, на доверии.',
     ['outdoor-library.jpg']),
    ('Сеть датчиков качества воздуха', 'ИТ',
     'Двадцать станций на столбах и крышах; данные открытые, карта '
     'обновляется каждые пять минут.',
     ['programmer.jpg', 'open-source-crm.jpg']),
]


# Порядок сумм «нужно» — от небольшой инициативы до серьёзной стройки.
REQUIRED_STEPS = [180000, 340000, 620000, 900000, 1450000, 2400000,
                  3800000, 5200000, 8500000, 12000000]


def load_projects(env, extra=100):
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

    seen = {}
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
        photo_file = _photo_for(row, seen)
        photo = os.path.join(PHOTO_DIR, photo_file) if photo_file else ''
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


def _photo_for(row, seen):
    """Имя файла со снимком для строки каталога.

    Названия в выгрузке повторяются, поэтому кадр выбирается по счётчику
    вхождений: пять «Круглогодичных теплиц» подряд с одной и той же
    фотографией читаются как сбой загрузки, а не как пять проектов.
    """
    photos = PHOTOS_BY_NAME.get(row['name'])
    if not photos:
        # Дописанные проекты несут файл прямо в строке; для незнакомого
        # названия из выгрузки остаётся то, что было в ней указано.
        return os.path.basename(row['photo']) if row['photo'] else ''
    count = seen.get(row['name'], 0)
    seen[row['name']] = count + 1
    return photos[count % len(photos)]


def _extra_rows(rows, extra, rnd):
    """Дописать проектов сверх макета.

    Решение владельца: опубликованных должно быть больше ста. После
    того как часть уйдёт в черновики по нехватке верификации у
    инициатора, ста из ста не остаётся — значит записей нужно больше.

    Названия собираются из тех же тем и городов, что в макете, а не
    нумерацией: «Проект №117» — это не пример, а заполнитель.
    """
    cities = sorted({row['city'] for row in rows})
    # Рубрика и подрубрика берутся у любой строки выгрузки с той же
    # темой: подрубрики заведены только под своей рубрикой, и придумать
    # их здесь заново значило бы завести второй, расходящийся словарь.
    sample = {}
    for row in rows:
        sample.setdefault(row['category'], row)
    # Теми же словами, что в выгрузке: их переводит в код словарь KIND,
    # и готовый код здесь превратился бы в «Кооперативный» по умолчанию.
    kinds = ['Кооперативный', 'Коммерческий', 'Некоммерческий', 'ДАО']

    extras = []
    for i in range(extra):
        name, theme, description, photos = EXTRA_PROJECTS[i % len(EXTRA_PROJECTS)]
        source = sample.get(theme) or rows[0]
        city = cities[(i * 3) % len(cities)]
        extras.append({
            'name': '%s — %s' % (name, city),
            'description': description,
            'city': city,
            'category': theme,
            'subcategory': source['subcategory'],
            'project_type': kinds[i % len(kinds)],
            # Каждый седьмой собран полностью: иначе запуск проекта и
            # передачу его в модуль управления проверить не на чем —
            # в макете готовность нигде не доходит до ста.
            'readiness': 100 if i % 7 == 3 else rnd.randint(8, 99),
            'photo': photos[(i // len(EXTRA_PROJECTS)) % len(photos)],
        })
    return extras
