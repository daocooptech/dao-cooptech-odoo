# -*- coding: utf-8 -*-
"""Словарь характеристик по рубрикам и значения у объявлений.

Без данных панель фильтров не отладить: пустой фильтр выглядит сломанным,
и не видно ни характеристик, заполненных у двух объявлений из ста, ни
того, как ведут себя диапазоны.

Характеристика принадлежит платформе, а рубрике — привязка к ней. Марка
нужна и в автомобилях, и в запчастях; заводить её дважды значит получить
два несводимых списка марок и два фильтра, которые ищут разное под одним
названием.
"""
import logging
import random

_logger = logging.getLogger(__name__)

# Характеристики: ключ, название, тип, единица, как фильтруется,
# показывать ли в карточке, варианты значений.
#
# Ключ — адрес значения внутри объявления, а не подпись на экране: после
# первого использования он не меняется, иначе значения станут невидимыми.
ATTRIBUTES = [
    # ── Транспорт ──────────────────────────────────────────────────────
    ('brand', 'Марка', 'selection', '', 'checkbox', True,
     ['ГАЗ', 'КамАЗ', 'УАЗ', 'Лада', 'МТЗ', 'Toyota', 'Volkswagen',
      'Hyundai', 'Kia', 'Renault']),
    ('year', 'Год выпуска', 'integer', '', 'range', True, []),
    ('mileage_km', 'Пробег', 'integer', 'км', 'range', True, []),
    ('gearbox', 'Коробка передач', 'selection', '', 'checkbox', False,
     ['Механическая', 'Автоматическая', 'Вариатор']),
    ('engine_volume', 'Объём двигателя', 'float', 'л', 'range', False, []),
    ('drive', 'Привод', 'selection', '', 'checkbox', False,
     ['Передний', 'Задний', 'Полный']),
    ('condition', 'Состояние', 'selection', '', 'checkbox', True,
     ['Новое', 'Отличное', 'Рабочее', 'Требует ремонта']),

    # ── Недвижимость ───────────────────────────────────────────────────
    ('area_m2', 'Площадь', 'float', 'м²', 'range', True, []),
    ('rooms', 'Комнат', 'integer', '', 'checkbox', True, []),
    ('floor', 'Этаж', 'integer', '', 'range', False, []),
    ('floors_total', 'Этажей в здании', 'integer', '', 'range', False, []),
    ('build_year', 'Год постройки', 'integer', '', 'range', False, []),
    ('utilities', 'Коммуникации', 'tags', '', 'checkbox', False,
     ['Электричество', 'Вода', 'Газ', 'Канализация', 'Отопление',
      'Интернет']),
    ('land_sotka', 'Участок', 'float', 'сот.', 'range', True, []),

    # ── Продовольственные товары ───────────────────────────────────────
    ('lot_kg', 'Объём партии', 'float', 'кг', 'range', True, []),
    ('shelf_life_days', 'Срок годности', 'integer', 'дн.', 'range', False, []),
    ('storage', 'Условия хранения', 'selection', '', 'checkbox', False,
     ['Комнатная температура', 'Прохладное место', 'Холодильник',
      'Заморозка']),
    ('organic', 'Без химии', 'boolean', '', 'switch', True, []),
    ('packaging', 'Упаковка', 'selection', '', 'checkbox', False,
     ['Без упаковки', 'Мешок', 'Ящик', 'Банка', 'Вакуум']),

    # ── Металлопрокат и стройматериалы ─────────────────────────────────
    ('rolled_kind', 'Вид проката', 'selection', '', 'checkbox', True,
     ['Арматура', 'Лист', 'Труба', 'Уголок', 'Швеллер', 'Балка', 'Круг']),
    ('steel_grade', 'Марка стали', 'selection', '', 'checkbox', True,
     ['Ст3сп', 'Ст3пс', '09Г2С', '20', '40Х', 'AISI 304']),
    ('gost', 'ГОСТ', 'char', '', 'none', False, []),
    ('thickness_mm', 'Толщина', 'float', 'мм', 'range', True, []),
    ('length_m', 'Длина', 'float', 'м', 'range', False, []),
    ('lot_ton', 'Партия', 'float', 'т', 'range', True, []),

    # ── Оборудование и инструменты ─────────────────────────────────────
    ('power_kw', 'Мощность', 'float', 'кВт', 'range', True, []),
    ('voltage', 'Питание', 'selection', '', 'checkbox', False,
     ['220 В', '380 В', 'Аккумулятор', 'Бензин', 'Дизель']),
    ('with_operator', 'С оператором', 'boolean', '', 'switch', True, []),
    ('warranty_months', 'Гарантия', 'integer', 'мес.', 'range', False, []),

    # ── Электроника ────────────────────────────────────────────────────
    ('ram_gb', 'Оперативная память', 'integer', 'ГБ', 'checkbox', False, []),
    ('storage_gb', 'Накопитель', 'integer', 'ГБ', 'range', False, []),
    ('screen_inch', 'Экран', 'float', '″', 'range', False, []),
]

# Какие характеристики к какой рубрике. Ключ — название рубрики или
# подрубрики; привязка к родительской действует и на дочерние.
ASSIGNMENTS = {
    'Транспорт': ['year', 'condition'],
    'Легковые автомобили': ['brand', 'mileage_km', 'gearbox',
                            'engine_volume', 'drive'],
    'Грузовики и спецтехника': ['brand', 'mileage_km', 'power_kw',
                                'with_operator'],
    'Аренда спецтехники': ['power_kw', 'with_operator'],

    'Недвижимость': ['area_m2', 'utilities'],
    'Дома, дачи, коттеджи': ['rooms', 'land_sotka', 'build_year'],
    'Земельные участки': ['land_sotka'],
    'Склады и коммерческая недвижимость': ['floor', 'floors_total'],
    'Гаражи и машиноместа': ['floor'],

    'Продовольственные товары': ['lot_kg', 'organic', 'storage'],
    'Овощи и фрукты': ['packaging'],
    'Крупы, мука и бакалея': ['shelf_life_days', 'packaging'],
    'Мясная и молочная продукция': ['shelf_life_days'],
    'Мёд и продукты пчеловодства': ['shelf_life_days', 'packaging'],

    'Ремонт и стройматериалы': ['rolled_kind', 'steel_grade', 'gost',
                                'thickness_mm', 'length_m', 'lot_ton'],
    'Инструменты': ['power_kw', 'voltage', 'condition'],

    'Бизнес и оборудование': ['condition'],
    'Оборудование для бизнеса': ['power_kw', 'voltage', 'warranty_months'],

    'Электроника': ['condition'],
    'Ноутбуки и компьютеры': ['ram_gb', 'storage_gb', 'screen_inch'],
    'Видео и аудио': ['warranty_months'],
    'Оргтехника': ['warranty_months'],

    'Хобби и отдых': ['condition'],
    'Велосипеды': ['brand'],
}


def load_attributes(env):
    """Завести справочник и проставить значения у объявлений."""
    Attribute = env['coop.attribute'].sudo()
    Option = env['coop.attribute.option'].sudo()
    Assignment = env['coop.attribute.assignment'].sudo()
    Category = env['coop.resource.category'].sudo()

    by_code = {}
    for index, (code, name, value_type, unit, widget, on_card, options) in \
            enumerate(ATTRIBUTES):
        attribute = Attribute.search([('code', '=', code)], limit=1)
        values = {
            'name': name,
            'value_type': value_type,
            'unit': unit,
            'filter_widget': widget,
            'show_on_card': on_card,
            # Индексируем то, по чему фильтруют диапазоном: там перебор
            # дороже всего.
            'is_indexed': widget == 'range',
            'sequence': (index + 1) * 10,
        }
        if attribute:
            attribute.write(values)
        else:
            attribute = Attribute.create(dict(values, code=code))
        by_code[code] = attribute

        for order, label in enumerate(options):
            option_code = _slug(label)
            option = Option.search([('attribute_id', '=', attribute.id),
                                    ('code', '=', option_code)], limit=1)
            if not option:
                Option.create({
                    'attribute_id': attribute.id,
                    'name': label,
                    'code': option_code,
                    'sequence': (order + 1) * 10,
                })

    linked = 0
    for category_name, codes in ASSIGNMENTS.items():
        category = Category.search([('name', '=', category_name)], limit=1)
        if not category:
            _logger.info('Характеристики: рубрика «%s» не найдена',
                         category_name)
            continue
        for order, code in enumerate(codes):
            attribute = by_code.get(code)
            if not attribute:
                continue
            exists = Assignment.search_count([
                ('attribute_id', '=', attribute.id),
                ('category_id', '=', category.id)])
            if exists:
                continue
            Assignment.create({
                'attribute_id': attribute.id,
                'category_id': category.id,
                'sequence': (order + 1) * 10,
            })
            linked += 1

    filled = _fill_values(env, by_code)
    _logger.info('Характеристики: %s штук, %s привязок, значения у %s '
                 'объявлений', len(by_code), linked, filled)
    return filled


def _slug(label):
    """Устойчивый ключ варианта: латиницей, строчными, без пробелов."""
    table = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    }
    out = []
    for char in label.lower():
        if char in table:
            out.append(table[char])
        elif char.isalnum():
            out.append(char)
        elif out and out[-1] != '_':
            out.append('_')
    return ''.join(out).strip('_') or 'x'


def _fill_values(env, by_code):
    """Проставить значения у объявлений тех рубрик, где они заведены.

    Значения правдоподобные, а не случайные: пробег легковой машины и
    пробег грузовика различаются на порядок, и фильтр по диапазону на
    случайных числах ничего не покажет.
    """
    Resource = env['coop.resource'].sudo()
    rnd = random.Random(20260903)
    filled = 0

    for resource in Resource.search([('category_id', '!=', False)]):
        definition = resource.category_id.attribute_definition or []
        codes = [item.get('name') for item in definition]
        if not codes:
            continue
        values = {}
        for code in codes:
            value = _value_for(code, resource, rnd, by_code)
            if value is not None:
                values[code] = value
        if not values:
            continue
        # Точка сохранения на объявление: PostgreSQL обрывает транзакцию
        # на первой ошибке, и без неё одна плохая запись унесла бы весь
        # остаток каталога.
        with env.cr.savepoint():
            resource.attrs = values
            filled += 1
    return filled


def _value_for(code, resource, rnd, by_code):
    """Правдоподобное значение характеристики для этого объявления."""
    # Часть характеристик намеренно оставляем пустыми: в жизни объявление
    # заполнено не полностью, и фильтр обязан это переживать.
    if rnd.random() < 0.15:
        return None

    attribute = by_code.get(code)
    if attribute and attribute.value_type in ('selection', 'tags'):
        options = attribute.option_ids
        if not options:
            return None
        if attribute.value_type == 'tags':
            picked = rnd.sample(list(options), k=min(len(options),
                                                     rnd.randint(1, 3)))
            return [option.code for option in picked]
        return rnd.choice(list(options)).code

    ranges = {
        'year': (1998, 2026),
        'mileage_km': (5_000, 480_000),
        'engine_volume': (1.2, 6.5),
        'area_m2': (18, 1200),
        'rooms': (1, 6),
        'floor': (1, 12),
        'floors_total': (1, 16),
        'build_year': (1955, 2025),
        'land_sotka': (4, 250),
        'lot_kg': (5, 12_000),
        'shelf_life_days': (3, 720),
        'thickness_mm': (0.5, 40),
        'length_m': (1, 12),
        'lot_ton': (0.2, 60),
        'power_kw': (0.4, 180),
        'warranty_months': (0, 36),
        'ram_gb': (4, 64),
        'storage_gb': (128, 4096),
        'screen_inch': (11.6, 32),
    }
    if code in ranges:
        low, high = ranges[code]
        if isinstance(low, float) or isinstance(high, float):
            return round(rnd.uniform(low, high), 1)
        return rnd.randint(low, high)

    if code == 'organic':
        return rnd.random() < 0.4
    if code == 'with_operator':
        return rnd.random() < 0.5
    if code == 'gost':
        return rnd.choice(['ГОСТ 5781-82', 'ГОСТ 8240-97', 'ГОСТ 8509-93',
                           'ГОСТ 19903-2015', 'ГОСТ 3262-75'])
    return None
