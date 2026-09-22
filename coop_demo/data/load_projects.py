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
from datetime import timedelta

from . import emblems
from .dao_projects import (DAO_FROM_MOCKUP, DAO_PROJECTS, IT_SUBCATEGORIES,
                           MOCKUP_CATEGORY_FIX)

from odoo import fields

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


# Снимки, которыми иллюстрируются проекты про код и узлы. Взяты те, что
# показывают работу, а не предмет: у распределённого реестра предмета
# нет, а люди за работой есть.
IT_PHOTO_STEMS = ('server-rack', 'programmer', 'coding-class', 'laptop-desk',
                  'office-desk', 'printer3d-arm', 'printer3d-nozzle')


def _it_photo(name):
    """Снимок для ДАО-проекта: свой у каждого, устойчиво по названию."""
    import glob
    import zlib
    # Ищем в обеих папках: у проектов своих ИТ-снимков четыре, а
    # добор по запросам про сервера и разработку лёг к ресурсам — их там
    # три десятка. Двадцати ДАО-проектам четырёх мало: владелец просил
    # «сделай все разные».
    folders = [PHOTO_DIR, os.path.join(os.path.dirname(PHOTO_DIR), 'resources')]
    files = []
    for folder in folders:
        for base in IT_PHOTO_STEMS:
            files.extend(sorted(glob.glob(os.path.join(folder, base + '*.jpg'))))
    if not files:
        return None
    path = files[zlib.crc32((name or '').encode('utf-8')) % len(files)]
    with open(path, 'rb') as fh:
        return base64.b64encode(fh.read())


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
    # ДАО-проект заводит ДАО или человек, а не ИП с пилорамой. Форма
    # «децентрализованная автономная организация» в справочнике есть, и
    # организации с ней в каталоге тоже.
    dao_orgs = [org for org in companies
                if org.coop_legal_form_id.code == 'dao']
    if not initiators:
        _logger.warning('Нет участников — каталог проектов не наполняю')
        return

    rnd = random.Random(20260902)
    today = fields.Date.today()
    created = updated = 0

    seen = {}
    for index, row in enumerate(rows + _extra_rows(rows, extra, rnd)):
        key = 'projects.json#%s' % index
        initiator = _initiator_for(row, index, initiators, dao_orgs, people)
        required = row.get('required') or REQUIRED_STEPS[
            index % len(REQUIRED_STEPS)]
        readiness = max(1, min(100, int(row['readiness'])))
        category, subcategory = _category_for(row)

        values = {
            'name': row['name'],
            'date_deadline': _deadline_for(index, rnd, today),
            'funding_rule': _rule_for(index),
            'funding_threshold': 70,
            'fallback_plan': _fallback_for(row),
            'contribution_basis': _basis_for(row),
            'summary': row['description'],
            'description': '<p>%s</p>' % row['description'] if row['description'] else False,
            'city': row['city'],
            'kind': _kind_for(row),
            'category_id': categories.get(category, {}).get('id'),
            'subcategory_id': categories.get(category, {}).get(
                'children', {}).get(subcategory),
            'partner_id': initiator.id,
            'author_id': (initiator if not initiator.is_company
                          else people[index % len(people)]).id,
            'required_total': required,
            'import_key': key,
        }
        if row.get('emblem'):
            # Раньше ДАО-проект получал знак: предмет у него — код, узел,
            # реестр, и фотография ноутбука на двадцати плитках подряд
            # читалась бы как сбой загрузки.
            #
            # Владелец 15 сентября 2026 сказал иначе: «непонятные иконки
            # вместо картинок». Довод про однообразие снят добором
            # снимков: по запросам про сервера, разработку и обучение их
            # набралось три десятка, и каждому ДАО-проекту достаётся
            # свой. Знак остаётся запасным — если снимков не хватит.
            values['image_1920'] = (_it_photo(row['name'])
                                    or emblems.dao_mark(row['name'],
                                                        row['emblem']))
        else:
            photo_file = _photo_for(row, seen)
            photo = os.path.join(PHOTO_DIR, photo_file) if photo_file else ''
            if photo and os.path.exists(photo):
                with open(photo, 'rb') as fh:
                    values['image_1920'] = base64.b64encode(fh.read())

        project = Project.search([('import_key', '=', key)], limit=1)
        if project:
            # «Нужно» у проекта со вкладами не переписываем: вклады
            # построены под него один раз, а шаг по порядковому номеру
            # съезжает от любой правки списка доборных проектов — и
            # отношение двух правдоподобных чисел становится ложью.
            if project.contribution_ids:
                values.pop('required_total', None)
            project.write(values)
            updated += 1
        else:
            project = Project.create(values)
            created += 1

        # Состояние решается до вкладов, а не после: готовность у записи
        # считается от вкладов, и брать её как основание для выбора
        # состояния значит смотреть на то, что сам же и создал.
        #
        # Вклады у черновика при этом не удаляем, хотя «идея, собравшая
        # деньги» и выглядит противоречием. Полсотни таких — не ошибка
        # загрузчика: это проекты, снятые с публикации по нехватке ступени
        # у инициатора (`load_verification._demote_unpublishable`). Они
        # собирали по-настоящему, и стирать собранное нельзя. Что у такого
        # состояния должно быть своё имя, а не «Идея», — вопрос к
        # владельцу, а не повод терять данные.
        _set_economic_model(env, project, row, index)
        _fix_basis(env, project)
        state = _state_for(readiness, index)
        if not project.contribution_ids:
            _make_contributions(Contribution, project, required, readiness,
                               people, rnd, index)
        else:
            _realign_required(project, readiness)
        # Заморозка — не просто состояние: проект помнит, куда вернётся,
        # и объявления с него снимаются. Пишем через `write`, чтобы
        # сработал тот же код, что и у кнопки.
        if state == 'frozen':
            # Куда вернётся — по готовности: собранный проект замораживают
            # уже запущенным, недособранный остаётся в сборе.
            back = 'running' if project.readiness >= 100 else 'gathering'
            project.write({'resume_state': back, 'state': state})
        else:
            project.state = state

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
    # Разделы ИТ заводятся своим списком: в выгрузке макета под этой
    # темой был один раздел на всё, и лежали в нём сушильный комплекс и
    # медпункт. Чем занимаются ДАО на самом деле — см. `dao_projects`.
    tree.setdefault('ИТ', set()).update(IT_SUBCATEGORIES)

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


def _realign_required(project, readiness):
    """Вернуть «нужно» в соответствие с уже заведёнными вкладами.

    Вклады строятся из готовности один раз и больше не трогаются, а
    «нужно» переписывалось при каждом проходе — значением из шага по
    порядковому номеру записи. Стоило списку доборных проектов
    измениться, и номера съезжали: у одного проекта под тремя
    миллионами вкладов оставалось «нужно 340 000», то есть девятьсот
    семьдесят процентов готовности.

    Ошибки при этом нет ни одной: обе величины по отдельности
    правдоподобны, врёт только их отношение.

    Считаем обратно — от вкладов и от готовности, записанной в макете.
    Расхождение меньше пяти процентных пунктов не трогаем: там просто
    округление.
    """
    if not readiness or project.readiness == readiness:
        return 0
    if abs(project.readiness - readiness) <= 5:
        return 0
    new_one = round(project.contribution_total * 100.0 / readiness)
    # Предохранитель. Расчёт «нужно» от вкладов сам по себе верен, но он
    # делается при каждом прогоне наполнения, а `project.readiness` в
    # этот момент может быть ещё не пересчитан — и тогда каждый прогон
    # умножает сумму. Так у «Цеха переработки шерсти» набежало
    # 28 157 252 501 996 113 920 ₽: ошибки нет ни на одном шаге, врёт
    # только накопление.
    #
    # Кооперативный проект в двадцать раз дороже самого дорогого шага
    # наполнения — это уже не проект, а сбой. Такое не пишем.
    limit = REQUIRED_STEPS[-1] * 3
    if new_one > limit:
        _logger.warning(
            'Проект «%s»: расчёт «нужно» дал %s — это больше предела, '
            'оставляю как было', project.name, new_one)
        return 0
    project.required_total = new_one
    return 1


def repair_scales(env):
    """Вернуть разогнавшиеся суммы в человеческий вид.

    Разгон случился до предохранителя выше и остался в данных: у
    двадцати пяти проектов «нужно» дошло до квинтиллионов, а вместе с
    ним и вклады — полторы тысячи записей дороже ста миллионов.

    Чиним от источника: «нужно» у проекта берётся из того же шага, что
    и при заведении (ключ импорта хранит порядковый номер), а вклады
    пересчитываются пропорционально, чтобы готовность осталась той же.
    Идём только по тем, у кого сумма за пределом, — проход безвреден
    при повторном запуске.
    """
    # Втрое дороже самого дорогого шага наполнения — уже не проект, а
    # накопленный разгон: в макете самый крупный просит двенадцать
    # миллионов, и тридцать шесть это щедрый запас.
    limit = REQUIRED_STEPS[-1] * 3
    projects = env['coop.project'].sudo().search(
        [('required_total', '>', limit)])
    fixed = 0
    for project in projects:
        key = project.import_key or ''
        number = 0
        if '#' in key:
            try:
                number = int(key.rsplit('#', 1)[1])
            except ValueError:
                number = 0
        needed = REQUIRED_STEPS[number % len(REQUIRED_STEPS)]
        readiness = max(1, min(300, project.readiness or 100))
        collect = round(needed * readiness / 100.0)
        contributions = project.contribution_ids
        was = sum(contributions.mapped('value')) or 1
        # Пропорция сохраняется: у кого вклад был вдвое больше соседнего,
        # таким и останется. Переписывать вклады поровну значило бы
        # стереть след того, кто внёс больше всех.
        for contribution in contributions:
            contribution.value = round(contribution.value * collect / was)
        project.required_total = needed
        fixed += 1
    if fixed:
        _logger.info('Суммы проектов приведены в порядок: %s', fixed)
    return fixed


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


# Правовая форма под вид проекта. Экономическая модель — это правовая
# форма плюс налоговый режим (решение владельца 283), и справочник из
# шестидесяти четырёх сочетаний на платформе есть. А в каталоге его не
# было ни у одного проекта из двухсот девятнадцати, кроме одного: вкладка
# «Форма собственности» стояла пустой, и весь разбор — управление,
# налоги, ответственность, что важно вкладывающемуся — прочитать было
# негде.
#
# Форма выводится из вида проекта, а не берётся наугад: у кооперативного
# проекта не бывает акционерного общества, а у коммерческого —
# потребительского кооператива.
FORMS_BY_KIND = {
    'cooperative': ['po', 'pk', 'spk', 'sppk', 'kpk'],
    'commercial': ['ooo', 'ao', 'ip', 'hoz_part'],
    'nonprofit': ['ano', 'fond', 'oo', 'association'],
    # У ДАО правовой формы в России нет: организация всё равно
    # регистрируется чем-то из существующего. Разработку чаще ведут через
    # ООО, а общее дело участников — через потребительский кооператив.
    'dao': ['ooo', 'po', 'ano'],
}


def _set_economic_model(env, project, row, index):
    """Проставить экономическую модель по виду проекта."""
    if project.economic_model_id:
        return 0
    Model = env['coop.economic.model'].sudo()
    codes = FORMS_BY_KIND.get(project.kind, ['ooo'])
    code = codes[index % len(codes)]
    models = Model.search([('legal_form_id.code', '=', code)], order='id')
    if not models:
        return 0
    project.economic_model_id = models[index % len(models)].id
    return 1


def _fix_basis(env, project):
    """Свести основание сбора с тем, кто на самом деле вложился.

    Паевой взнос вносит только пайщик — платформа это проверяет. В
    наполнении же деньги в кооперативный проект несут кто угодно: состав
    вкладчиков собран раньше, чем появилось основание сбора, и членство
    там не при чём.

    Спорить с собственной проверкой не будем и подделывать членство тоже:
    основание опускается до пожертвования, а «паевой взнос» остаётся у
    тех проектов, где вкладчики действительно пайщики.
    """
    if project.contribution_basis != 'share':
        return 0
    org = project.partner_id
    money = project.contribution_ids.filtered(
        lambda c: c.state == 'accepted' and c.kind == 'money')
    if not money:
        return 0
    if not org.is_company:
        project.contribution_basis = 'donation'
        return 1
    members = set(env['coop.membership'].sudo().search([
        ('organization_id', '=', org.id), ('state', '=', 'active'),
    ]).mapped('partner_id').ids)
    if not set(money.mapped('partner_id').ids) <= members:
        project.contribution_basis = 'donation'
        return 1
    return 0


def _deadline_for(index, rnd, today):
    """Срок сбора с разбросом, часть — уже просроченная.

    Просроченные нужны: по ним и видно, как крон закрывает сбор. Без них
    состояние «Сбор не удался» в каталоге не на чем проверить.
    """
    if index % 11 == 4:
        return today - timedelta(days=rnd.randint(1, 40))
    return today + timedelta(days=rnd.randint(14, 180))


def _rule_for(index):
    """Правило закрытия. Умолчание — от порога (решение владельца 294).

    «Оставляем собранное» даётся редко и только пожертвованиям: при
    предоплате оговорка «возврат не производится» ничтожна, и схема
    оборачивается необеспеченным обязательством.
    """
    if index % 9 == 3:
        return 'all_or_nothing'
    if index % 17 == 8:
        return 'keep_all'
    return 'threshold'


def _basis_for(row):
    """Правовое основание денежного вклада.

    Кооперативный проект собирает паевые взносы, некоммерческий —
    пожертвования, остальные — предоплату за вознаграждение.
    Инвестирование в наполнении не ставим: на узле оно закрыто, пока нет
    статуса оператора инвестиционной платформы.
    """
    return {
        'Кооперативный': 'share',
        'Некоммерческий': 'donation',
    }.get(row['project_type'], 'prepay')


def _fallback_for(row):
    """Что будет сделано, если соберут не всё.

    Обязательно у всех, кто может запуститься на неполном сборе:
    вкладчик читает не «порог 70 %», а что именно он получит при
    семидесяти процентах. Текст выводится из самого проекта — общая
    отписка вроде «сделаем что успеем» тут хуже пустого поля.
    """
    name = (row['name'] or 'проект').split(' — ')[0].strip().lower()
    return ('Соберём не всё — запустим первую очередь: %s в меньшем '
            'объёме, без второй площадки и без запаса по оборудованию. '
            'Недостающее добираем вкладами по ходу работы, о каждом '
            'сокращении пишем в ленту проекта до того, как начать.'
            % name)


def _initiator_for(row, index, initiators, dao_orgs, people):
    """От чьего имени собирается проект.

    У ДАО-проекта инициатор не любой: «ИП Ковалёва» в роли затейника
    сети узлов читается как ошибка наполнения. Заводят такое сами ДАО —
    их в каталоге шесть — и люди: настоящая ДАО и начинается с
    нескольких человек, а организация появляется потом.
    """
    if row.get('is_dao') or row['name'] in DAO_FROM_MOCKUP:
        pool = list(dao_orgs) + list(people[:12])
        if pool:
            return pool[index % len(pool)]
    return initiators[(index * 5) % len(initiators)]


def _kind_for(row):
    """Вид проекта — из существа дела, а не из пометки в выгрузке.

    В выгрузке макета `project_type` расставлен так же наугад, как
    рубрики: ДАО там значатся сыроварня, теплица и пункт приёма
    вторсырья. Владелец 14 сентября 2026: «дао проекты в основном в ит
    сфере». ДАО работает там, где вклад проверяем без доверия к
    участнику, — это про код, а не про лопату.
    """
    if row.get('is_dao') or row['name'] in DAO_FROM_MOCKUP:
        return 'dao'
    kind = KIND.get(row['project_type'], 'cooperative')
    return 'cooperative' if kind == 'dao' else kind


def _category_for(row):
    """Тема и раздел, с поправкой на ошибки выгрузки."""
    fix = MOCKUP_CATEGORY_FIX.get(row['name'])
    if fix and row['category'] == 'ИТ':
        return fix
    return row['category'], row['subcategory']


def _state_for(readiness, index):
    """Состояние по готовности из выгрузки, с разбросом.

    Готовность берётся из строки макета, а не у записи: у записи она
    считается от вкладов, а вклады заводятся после того, как состояние
    уже выбрано.

    Идеи, замороженные и отменённые нужны, чтобы соответствующие
    экраны было на чём проверить; их доли небольшие — каталог должен
    оставаться каталогом.
    """
    if index % 29 == 7:
        return 'draft'
    if index % 37 == 11:
        return 'cancelled'
    # Заморозка — не отмена: проект стоит, но жив. Без таких записей в
    # каталоге не видно ни пометки на плитке, ни кнопки «Возобновить».
    if index % 23 == 5:
        return 'frozen'
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
    #
    # ДАО в этом круге больше нет. Раньше вид раздавался по очереди —
    # каждый четвёртый проект становился ДАО независимо от того, что он
    # такое, и в каталоге заводилась «Сыроварня — ДАО». ДАО-проекты
    # заводятся отдельно, своим списком и своим предметом.
    kinds = ['Кооперативный', 'Коммерческий', 'Некоммерческий']

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
    return extras + _dao_rows(rnd)


def _dao_rows(rnd):
    """ДАО-проекты: предмет, которым ДАО занимаются на самом деле.

    Города нет намеренно. ДАО не привязана к месту: узлы стоят в разных
    городах, дежурство идёт по часовым поясам, переводчик живёт где
    живёт. Приписать такому проекту Волгоград значило бы соврать ради
    заполненного поля — и увести его в отбор по городу, где ему делать
    нечего.
    """
    rows = []
    for i, (name, subcategory, description, required, icon) in enumerate(
            DAO_PROJECTS):
        rows.append({
            'name': name,
            'description': description,
            'city': '',
            'category': 'ИТ',
            'subcategory': subcategory,
            'project_type': 'ДАО',
            'is_dao': True,
            'required': required,
            'emblem': icon,
            # Собранные тоже нужны: запуск проекта и передачу его в
            # модуль управления проверять не на чем, если ни один не
            # доведён до конца.
            'readiness': 100 if i % 6 == 2 else rnd.randint(12, 96),
            'photo': '',
        })
    return rows
