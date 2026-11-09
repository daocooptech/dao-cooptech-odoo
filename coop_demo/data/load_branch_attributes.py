# -*- coding: utf-8 -*-
"""Характеристики по веткам дерева каталога ресурсов (задача 399, 10.11.2026).

После перестройки дерева (№ 398) фильтры остались от старых рубрик:
металлопрокат висел на дровах, удобрениях и расходниках, пробег — на
перевозке и прицепах, а у квартир, комнат, мототехники, запчастей и
водного транспорта не было своих характеристик. Образцы (Авито, OLX, Юла)
дают в каждой ветке свой набор: у квартиры — комнаты, этаж, тип дома,
ремонт; у машины — кузов, топливо, мощность; у мотоцикла — тип и объём.

Привязки снимаются и ставятся здесь явно; уже заполненные значения не
затираются, пустые добираются. Идемпотентно.
"""
import logging
import random

from .load_attributes import _slug

_logger = logging.getLogger(__name__)

# ключ, название, тип, единица, виджет фильтра, в карточке, варианты
NEW_ATTRIBUTES = [
    ('flat_rooms', 'Комнат', 'selection', '', 'checkbox', True,
     ['Студия', '1', '2', '3', '4', '5+']),
    ('house_type', 'Тип дома', 'selection', '', 'checkbox', True,
     ['Панельный', 'Кирпичный', 'Монолитный', 'Блочный', 'Деревянный']),
    ('renovation', 'Ремонт', 'selection', '', 'checkbox', False,
     ['Без ремонта', 'Косметический', 'Евроремонт', 'Дизайнерский']),
    ('bathroom', 'Санузел', 'selection', '', 'checkbox', False,
     ['Совмещённый', 'Раздельный', 'Два и более']),
    ('balcony', 'Балкон или лоджия', 'boolean', '', 'switch', False, []),
    ('elevator', 'Лифт', 'boolean', '', 'switch', False, []),
    ('wall_material', 'Материал стен', 'selection', '', 'checkbox', True,
     ['Кирпич', 'Брус', 'Бревно', 'Газобетон', 'Каркас', 'Монолит']),
    ('commercial_purpose', 'Назначение', 'selection', '', 'checkbox', True,
     ['Торговое', 'Офис', 'Общепит', 'Склад', 'Производство', 'Услуги']),
    ('separate_entrance', 'Отдельный вход', 'boolean', '', 'switch', False, []),
    ('ceiling_height_m', 'Высота потолков', 'float', 'м', 'range', False, []),
    ('warehouse_class', 'Класс склада', 'selection', '', 'checkbox', True,
     ['A', 'B', 'C', 'D']),
    ('heated', 'Отапливаемый', 'boolean', '', 'switch', False, []),
    ('ramp', 'Пандус', 'boolean', '', 'switch', False, []),
    ('gates_count', 'Ворот', 'integer', '', 'range', False, []),
    ('body_type', 'Кузов', 'selection', '', 'checkbox', True,
     ['Седан', 'Хэтчбек', 'Универсал', 'Внедорожник', 'Кроссовер',
      'Минивэн', 'Пикап']),
    ('fuel', 'Топливо', 'selection', '', 'checkbox', False,
     ['Бензин', 'Дизель', 'Газ', 'Гибрид', 'Электро']),
    ('engine_power_hp', 'Мощность двигателя', 'integer', 'л. с.', 'range',
     False, []),
    ('truck_kind', 'Вид', 'selection', '', 'checkbox', True,
     ['Бортовой', 'Самосвал', 'Фургон', 'Тягач', 'Рефрижератор', 'Автобус',
      'Микроавтобус']),
    ('capacity_ton', 'Грузоподъёмность', 'float', 'т', 'range', True, []),
    ('special_kind', 'Вид техники', 'selection', '', 'checkbox', True,
     ['Экскаватор', 'Погрузчик', 'Бульдозер', 'Автокран', 'Каток', 'Трактор',
      'Манипулятор']),
    ('engine_hours', 'Моточасы', 'integer', 'ч', 'range', False, []),
    ('moto_kind', 'Тип', 'selection', '', 'checkbox', True,
     ['Мотоцикл', 'Скутер', 'Квадроцикл', 'Снегоход', 'Питбайк']),
    ('engine_cc', 'Объём двигателя', 'integer', 'куб. см', 'range', False, []),
    ('part_kind', 'Вид запчасти', 'selection', '', 'checkbox', True,
     ['Шины', 'Диски', 'Двигатель и КПП', 'Кузовные детали',
      'Электрика и свет', 'Подвеска и тормоза']),
    ('tire_season', 'Сезон шин', 'selection', '', 'checkbox', False,
     ['Лето', 'Зима', 'Всесезонные']),
    ('tire_diameter', 'Диаметр шин', 'integer', '″', 'range', False, []),
    ('boat_kind', 'Вид', 'selection', '', 'checkbox', True,
     ['Лодка ПВХ', 'Моторная лодка', 'Катер', 'Гидроцикл', 'Яхта',
      'Байдарка']),
]

# Варианты марки по ветке: одна характеристика «Марка», разные списки.
BRANDS_ADD = ['Mazda', 'Skoda', 'Nissan', 'Ford', 'Chevrolet', 'BMW',
              'Mercedes-Benz', 'Mitsubishi', 'Chery', 'Haval', 'Geely',
              'Honda', 'Subaru', 'Yamaha', 'Suzuki', 'Kawasaki', 'Stels',
              'МАЗ', 'Isuzu', 'ПАЗ', 'Минск', 'Урал']
CARS = ['Toyota', 'Volkswagen', 'Hyundai', 'Kia', 'Renault', 'Лада', 'УАЗ',
        'Mazda', 'Skoda', 'Nissan', 'Ford', 'Chevrolet', 'BMW',
        'Mercedes-Benz', 'Mitsubishi', 'Chery', 'Haval', 'Geely', 'Honda',
        'Subaru']
TRUCKS = ['ГАЗ', 'КамАЗ', 'МАЗ', 'Isuzu', 'Hyundai', 'Ford', 'Mercedes-Benz',
          'Volkswagen', 'ПАЗ']
MOTOS = ['Yamaha', 'Honda', 'Suzuki', 'Kawasaki', 'Stels', 'Минск', 'Урал']

P = 'Недвижимость / '
T = 'Техника и транспорт / '
S = 'Сырьё и материалы / '
ROLLED = ['rolled_kind', 'steel_grade', 'gost', 'thickness_mm', 'length_m',
          'lot_ton']

# Что привязать (по полному имени рубрики), в порядке показа.
ASSIGN = {
    P + 'Жилая / Квартиры': ['flat_rooms', 'floor', 'floors_total',
                             'house_type', 'renovation', 'build_year',
                             'bathroom', 'balcony', 'elevator'],
    P + 'Жилая / Комнаты': ['floor', 'floors_total', 'house_type',
                            'renovation', 'build_year'],
    P + 'Жилая / Дома, дачи, коттеджи': ['wall_material', 'renovation',
                                         'utilities'],
    P + 'Коммерческая': ['commercial_purpose', 'floor', 'separate_entrance',
                         'ceiling_height_m'],
    P + 'Коммерческая / Склады': ['warehouse_class', 'heated', 'ramp',
                                  'gates_count'],
    P + 'Коммерческая / Производственные помещения': ['utilities', 'heated'],
    T + 'Легковые автомобили': ['body_type', 'fuel', 'engine_power_hp'],
    T + 'Грузовики и автобусы': ['truck_kind', 'capacity_ton', 'fuel'],
    T + 'Прицепы': ['capacity_ton'],
    T + 'Спецтехника': ['special_kind', 'engine_hours'],
    T + 'Мототехника': ['moto_kind', 'brand', 'engine_cc', 'mileage_km'],
    T + 'Запчасти и шины': ['part_kind', 'brand', 'tire_season',
                            'tire_diameter'],
    T + 'Водный транспорт': ['boat_kind', 'length_m', 'engine_power_hp'],
    S + 'Металлопрокат': ROLLED,
    'Услуги и финансы / Перевозка и доставка': ['capacity_ton'],
}

# Что снять (чужое после перестройки дерева).
REMOVE = {
    P.strip(' /'): ['utilities'],
    P + 'Гаражи и машиноместа': ['floor'],
    P + 'Коммерческая / Склады': ['floor', 'floors_total'],
    T + 'Грузовики и автобусы': ['power_kw', 'with_operator'],
    T + 'Прицепы': ['brand', 'mileage_km', 'power_kw', 'with_operator'],
    S + 'Дрова и топливо': ROLLED,
    S + 'Расходники для монтажа': ROLLED,
    S + 'Удобрения и субстрат': ROLLED,
    'Услуги и финансы / Перевозка и доставка': [
        'brand', 'mileage_km', 'power_kw', 'with_operator'],
}

# Сокращённый список марок для привязки «Марка» в ветке.
BRAND_POOLS = {
    T + 'Легковые автомобили': CARS,
    T + 'Грузовики и автобусы': TRUCKS,
    T + 'Мототехника': MOTOS,
    T + 'Запчасти и шины': CARS + TRUCKS[:3],
}

# Ветки, где добираются значения.
FILL = [
    P + 'Жилая / Квартиры', P + 'Жилая / Комнаты',
    P + 'Жилая / Дома, дачи, коттеджи', P + 'Коммерческая / Офисы',
    P + 'Коммерческая / Торговые помещения',
    P + 'Коммерческая / Помещения свободного назначения',
    P + 'Коммерческая / Производственные помещения',
    P + 'Коммерческая / Склады', T + 'Легковые автомобили',
    T + 'Грузовики и автобусы', T + 'Прицепы', T + 'Спецтехника',
    T + 'Мототехника', T + 'Запчасти и шины', T + 'Водный транспорт',
    S + 'Металлопрокат', 'Услуги и финансы / Перевозка и доставка',
]


def load_branch_attributes(env):
    """Завести характеристики, поправить привязки, добрать значения."""
    Attribute = env['coop.attribute'].sudo()
    Option = env['coop.attribute.option'].sudo()
    Assignment = env['coop.attribute.assignment'].sudo()
    Category = env['coop.resource.category'].sudo()

    def category(full_name):
        return Category.search([('complete_name', '=', full_name)], limit=1)

    base_seq = 1000
    for index, (code, name, value_type, unit, widget, on_card, options) in \
            enumerate(NEW_ATTRIBUTES):
        values = {'name': name, 'value_type': value_type, 'unit': unit,
                  'filter_widget': widget, 'show_on_card': on_card,
                  'is_indexed': widget == 'range',
                  'sequence': base_seq + index * 10}
        attribute = Attribute.search([('code', '=', code)], limit=1)
        if attribute:
            attribute.write(values)
        else:
            Attribute.create(dict(values, code=code))
        attribute = Attribute.search([('code', '=', code)], limit=1)
        _ensure_options(Option, attribute, options)

    # «Марка» и её варианты — общая; добавить недостающие марки.
    brand = Attribute.search([('code', '=', 'brand')], limit=1)
    if brand:
        _ensure_options(Option, brand, BRANDS_ADD)

    removed = 0
    for full_name, codes in REMOVE.items():
        cat = category(full_name)
        if not cat:
            _logger.info('Ветки: рубрика «%s» не найдена', full_name)
            continue
        found = Assignment.search([('category_id', '=', cat.id),
                                   ('attribute_id.code', 'in', codes)])
        removed += len(found)
        found.unlink()

    linked = 0
    for full_name, codes in ASSIGN.items():
        cat = category(full_name)
        if not cat:
            _logger.info('Ветки: рубрика «%s» не найдена', full_name)
            continue
        for order, code in enumerate(codes):
            attribute = Attribute.search([('code', '=', code)], limit=1)
            if not attribute:
                continue
            assignment = Assignment.search([
                ('attribute_id', '=', attribute.id),
                ('category_id', '=', cat.id)], limit=1)
            if not assignment:
                assignment = Assignment.create({
                    'attribute_id': attribute.id, 'category_id': cat.id,
                    'sequence': 100 + (order + 1) * 10})
                linked += 1
            pool = BRAND_POOLS.get(full_name) if code == 'brand' else None
            if pool:
                allowed = Option.search([('attribute_id', '=', attribute.id),
                                         ('code', 'in', [_slug(x) for x in pool])])
                assignment.option_ids = [(6, 0, allowed.ids)]
    # Марка в ветках с коротким списком: привязка у легковых и грузовых
    # уже была — сузить и её.
    for full_name, pool in BRAND_POOLS.items():
        cat = category(full_name)
        assignment = cat and Assignment.search([
            ('category_id', '=', cat.id), ('attribute_id.code', '=', 'brand')],
            limit=1)
        if assignment:
            allowed = Option.search([('attribute_id', '=', brand.id),
                                     ('code', 'in', [_slug(x) for x in pool])])
            assignment.option_ids = [(6, 0, allowed.ids)]

    env.flush_all()
    filled = _fill(env, category)
    _logger.info('Ветки: привязок поставлено %s, снято %s, значения у %s '
                 'объявлений', linked, removed, filled)
    return filled


def _ensure_options(Option, attribute, labels):
    for order, label in enumerate(labels):
        code = _slug(label)
        if not Option.search_count([('attribute_id', '=', attribute.id),
                                    ('code', '=', code)]):
            Option.create({'attribute_id': attribute.id, 'name': label,
                           'code': code, 'sequence': (order + 1) * 10 + 500})


def _current(resource):
    value = resource.attrs
    if hasattr(value, 'items'):
        return {k: v for k, v in value.items() if v not in (None, False, '')}
    return {item.get('name'): item.get('value') for item in (value or [])
            if isinstance(item, dict)
            and item.get('value') not in (None, False, '')}


def _fill(env, category):
    Resource = env['coop.resource'].sudo()
    Attribute = env['coop.attribute'].sudo()
    options = {}
    for attribute in Attribute.search([('value_type', 'in', ('selection', 'tags'))]):
        options[attribute.code] = {o.name: o.code for o in attribute.option_ids}
    filled = 0
    for full_name in FILL:
        cat = category(full_name)
        if not cat:
            continue
        for resource in Resource.search([('category_id', '=', cat.id)]):
            definition = [d.get('name') for d in
                          (resource.category_id.attribute_definition or [])]
            current = _current(resource)
            rnd = random.Random(resource.id * 7919 + 399)
            new = {}
            drop = set()
            for code in definition:
                have = current.get(code)
                merged = {**current, **new}
                hint = _hint(code, resource.name, options)
                if hint is not None:
                    new[code] = hint
                    continue
                if code in ('tire_season', 'tire_diameter') and \
                        merged.get('part_kind') not in ('shiny', 'diski'):
                    drop.add(code)      # шины описывают только шины и диски
                    continue
                if code == 'brand' and have and full_name in BRAND_POOLS:
                    labels = {options['brand'].get(x): x
                              for x in BRAND_POOLS[full_name]
                              if x in options['brand']}
                    if have in labels:
                        continue            # уже из допустимого списка
                elif have not in (None, False, '') and \
                        not _implausible(code, have, full_name, merged):
                    continue
                if rnd.random() < 0.1 and code not in (
                        'flat_rooms', 'truck_kind', 'moto_kind', 'part_kind',
                        'boat_kind', 'special_kind', 'brand'):
                    continue
                value = _generate(code, full_name, rnd, options, merged)
                if value is not None:
                    new[code] = value
            if new:
                with env.cr.savepoint():
                    resource.attrs = {k: v for k, v in
                                      {**current, **new}.items()
                                      if k not in drop}
                    filled += 1
    return filled


SPANS = {'Квартиры': (18, 140), 'Комнаты': (9, 26),
         'Дома, дачи, коттеджи': (60, 320), 'Офисы': (15, 300),
         'Торговые помещения': (20, 400),
         'Помещения свободного назначения': (30, 500),
         'Производственные помещения': (120, 3000), 'Склады': (100, 5000)}


def _implausible(code, value, branch, cur):
    """Значение от прежнего наполнения, не подходящее рубрике."""
    leaf = branch.rsplit(' / ', 1)[-1]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if code == 'area_m2' and leaf in SPANS:
        low, high = SPANS[leaf]
        return not (low <= number <= high)
    if code == 'floor' and cur.get('floors_total'):
        return number > float(cur['floors_total'])
    if code == 'floors_total' and leaf in ('Квартиры', 'Комнаты'):
        return number < 2
    if code == 'mileage_km' and leaf == 'Мототехника':
        return number > 80_000
    return False


def _hint(code, name, options):
    """Значение, прямо названное в заголовке объявления."""
    import re
    text = name.lower()

    def first(rules):
        for words, label in rules:
            if any(w in text for w in words):
                return options.get(code, {}).get(label)
        return None

    if code == 'flat_rooms':
        return first([(('студи',), 'Студия'), (('однокомнат', '1-комн'), '1'),
                      (('двушк', 'двухкомнат', '2-комн'), '2'),
                      (('трёшк', 'трехкомнат', 'трёхкомнат', '3-комн'), '3'),
                      (('четырёхкомнат', 'четырехкомнат'), '4')])
    if code == 'moto_kind':
        return first([(('скутер',), 'Скутер'), (('питбайк',), 'Питбайк'),
                      (('квадро',), 'Квадроцикл'), (('снегоход',), 'Снегоход'),
                      (('мотоцикл',), 'Мотоцикл')])
    if code == 'part_kind':
        return first([(('шин',), 'Шины'), (('диск',), 'Диски'),
                      (('двигател', 'кпп'), 'Двигатель и КПП'),
                      (('фонар', 'фар', 'генератор'), 'Электрика и свет'),
                      (('бампер', 'капот', 'крыл', 'дверь'),
                       'Кузовные детали'),
                      (('тормоз', 'амортизатор', 'подвеск'),
                       'Подвеска и тормоза')])
    if code == 'tire_season' and ('шин' in text or 'диск' in text):
        return first([(('зимн',), 'Зима'), (('летн',), 'Лето'),
                      (('всесезон',), 'Всесезонные')])
    if code == 'truck_kind':
        return first([(('самосвал',), 'Самосвал'),
                      (('микроавтобус',), 'Микроавтобус'),
                      (('автобус',), 'Автобус'), (('фургон',), 'Фургон'),
                      (('тягач',), 'Тягач'), (('рефриж',), 'Рефрижератор'),
                      (('борт',), 'Бортовой')])
    if code == 'boat_kind':
        return first([(('пвх',), 'Лодка ПВХ'), (('катер',), 'Катер'),
                      (('гидроцикл',), 'Гидроцикл'), (('яхт',), 'Яхта'),
                      (('байдарк',), 'Байдарка'),
                      (('лодк',), 'Моторная лодка')])
    if code == 'special_kind':
        return first([(('экскаватор',), 'Экскаватор'),
                      (('погрузчик',), 'Погрузчик'),
                      (('бульдозер',), 'Бульдозер'), (('кран',), 'Автокран'),
                      (('каток',), 'Каток'),
                      (('манипулятор',), 'Манипулятор'),
                      (('трактор',), 'Трактор')])
    if code == 'body_type':
        return first([(('универсал',), 'Универсал'), (('седан',), 'Седан'),
                      (('хэтчбек', 'хетчбек'), 'Хэтчбек'),
                      (('внедорожник',), 'Внедорожник'),
                      (('кроссовер',), 'Кроссовер'),
                      (('минивэн', 'минивен'), 'Минивэн'),
                      (('пикап',), 'Пикап')])
    if code == 'lot_ton':
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*тонн', text)
        return float(m.group(1).replace(',', '.')) if m else None
    if code == 'engine_cc':
        m = re.search(r'(\d{2,4})\s*куб', text)
        return int(m.group(1)) if m else None
    if code == 'tire_diameter' and ('шин' in text or 'диск' in text):
        m = re.search(r'\br(\d{2})\b', text)
        return int(m.group(1)) if m else None
    if code == 'year':
        m = re.search(r'\b((?:19|20)\d\d)\s*год', text)
        return int(m.group(1)) if m else None
    if code == 'capacity_ton':
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*т\b', text)
        return float(m.group(1).replace(',', '.')) if m else None
    return None


def _pick(options, code, labels, rnd):
    codes = [options[code][x] for x in labels if x in options.get(code, {})]
    return rnd.choice(codes) if codes else None


def _generate(code, branch, rnd, options, cur):
    flats = branch.endswith(('Квартиры', 'Комнаты'))
    if code == 'flat_rooms':
        return _pick(options, code, ['Студия', '1', '1', '2', '2', '3', '3',
                                     '4', '5+'], rnd)
    if code == 'area_m2':
        low, high = SPANS.get(branch.rsplit(' / ', 1)[-1], (18, 400))
        return round(rnd.uniform(low, high), 1)
    if code == 'floors_total':
        return rnd.randint(2, 25) if flats else rnd.randint(1, 5)
    if code == 'floor':
        top = cur.get('floors_total') or 12
        return rnd.randint(1, int(top))
    if code == 'build_year':
        return rnd.randint(1960, 2025)
    if code == 'house_type':
        return _pick(options, code, ['Панельный', 'Кирпичный', 'Монолитный',
                                     'Блочный', 'Панельный', 'Кирпичный'], rnd)
    if code in ('renovation', 'bathroom', 'wall_material', 'warehouse_class',
                'commercial_purpose', 'body_type', 'fuel', 'truck_kind',
                'special_kind', 'moto_kind', 'part_kind', 'tire_season',
                'boat_kind'):
        pools = {
            'commercial_purpose': {
                'Офисы': ['Офис', 'Услуги'],
                'Торговые помещения': ['Торговое', 'Общепит', 'Услуги'],
                'Производственные помещения': ['Производство', 'Склад'],
                'Склады': ['Склад'],
            },
            'warehouse_class': {'Склады': ['A', 'B', 'B', 'C', 'C', 'D']},
            'truck_kind': {'Грузовики и автобусы': [
                'Бортовой', 'Самосвал', 'Фургон', 'Тягач', 'Рефрижератор',
                'Автобус', 'Микроавтобус']},
            'fuel': {'Грузовики и автобусы': ['Дизель', 'Дизель', 'Газ'],
                     'Легковые автомобили': ['Бензин', 'Бензин', 'Дизель',
                                             'Гибрид', 'Электро', 'Газ']},
        }
        leaf = branch.rsplit(' / ', 1)[-1]
        labels = pools.get(code, {}).get(leaf) or list(options[code])
        if code in options:
            labels = [x for x in labels if x in options[code]] or list(
                options[code])
        return _pick(options, code, labels, rnd)
    if code in ('balcony', 'elevator', 'separate_entrance', 'heated', 'ramp'):
        return rnd.random() < 0.55
    if code == 'ceiling_height_m':
        return round(rnd.uniform(2.5, 6.0), 1)
    if code == 'gates_count':
        return rnd.randint(1, 8)
    if code == 'utilities':
        labels = ['Электричество', 'Вода', 'Газ', 'Канализация', 'Отопление',
                  'Интернет']
        picked = rnd.sample(labels, rnd.randint(2, 5))
        return [options['utilities'][x] for x in picked
                if x in options['utilities']]
    if code == 'rooms':
        return rnd.randint(2, 7)
    if code == 'land_sotka':
        return round(rnd.uniform(4, 40), 1)
    if code == 'brand':
        pool = BRAND_POOLS.get(branch)
        return _pick(options, 'brand', pool, rnd) if pool else None
    if code == 'year':
        return rnd.randint(2004, 2025) if 'Легков' in branch else \
            rnd.randint(1995, 2025)
    if code == 'mileage_km':
        age = max(1, 2026 - (cur.get('year') or 2015))
        top = 20_000 if 'Мото' not in branch else 8_000
        return min(rnd.randint(4_000, top) * age, 900_000 if 'Груз' in branch
                   else 450_000)
    if code == 'gearbox':
        return _pick(options, code, ['Механическая', 'Автоматическая',
                                     'Вариатор'], rnd)
    if code == 'engine_volume':
        return round(rnd.uniform(1.0, 4.5), 1)
    if code == 'drive':
        return _pick(options, code, ['Передний', 'Задний', 'Полный'], rnd)
    if code == 'engine_power_hp':
        if 'Водный' in branch:
            return rnd.choice([9, 15, 25, 40, 60, 90, 115, 150, 250])
        return rnd.randint(70, 330)
    if code == 'capacity_ton':
        if 'Прицепы' in branch:
            return round(rnd.uniform(0.5, 12), 1)
        return round(rnd.uniform(0.5, 25), 1)
    if code == 'engine_hours':
        return rnd.randint(200, 14_000)
    if code == 'engine_cc':
        return rnd.choice([50, 110, 125, 250, 400, 650, 800, 1000, 1200])
    if code == 'tire_diameter':
        return rnd.randint(13, 22)
    if code == 'length_m' and 'Водный' in branch:
        return round(rnd.uniform(2.5, 14), 1)
    if code == 'power_kw':
        return round(rnd.uniform(15, 250), 1)
    if code == 'condition':
        return _pick(options, code, ['Отличное', 'Рабочее', 'Рабочее',
                                     'Новое', 'Требует ремонта'], rnd)
    if code == 'rolled_kind':
        return _pick(options, code, list(options[code]), rnd)
    if code == 'steel_grade':
        return _pick(options, code, list(options[code]), rnd)
    if code == 'gost':
        return rnd.choice(['ГОСТ 5781-82', 'ГОСТ 8240-97', 'ГОСТ 8509-93',
                           'ГОСТ 19903-2015', 'ГОСТ 3262-75'])
    if code == 'thickness_mm':
        return round(rnd.uniform(0.5, 40), 1)
    if code == 'length_m':
        return round(rnd.uniform(1, 12), 1)
    if code == 'lot_ton':
        return round(rnd.uniform(0.2, 60), 1)
    return None
