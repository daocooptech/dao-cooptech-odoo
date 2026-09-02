# -*- coding: utf-8 -*-
"""Наполнение каталога ресурсов из макета.

Сто один ресурс из `resources.html`: предложения и спрос, четыре типа,
семь способов передачи, цена с единицей измерения, фотография.

Владельцы раздаются по каталогу участников. В макете владелец указан
только у двадцати трёх объявлений — приписан к названию через точку, — а
у остальных его нет вовсе. Оставить их без владельца нельзя: объявление
без того, кто за ним стоит, не объявление, а строка в таблице, и ни
написать по нему, ни оценить доверие невозможно.
"""
import base64
import json
import logging
import os

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
PHOTO_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img', 'resources')

TYPES = {
    'Материальный': 'material',
    'Оборудование': 'equipment',
    'Финансовый': 'financial',
    'Труд': 'labour',
}

METHODS = {
    'Продажа': 'sale',
    'Аренда': 'rent',
    'Рассрочка': 'installment',
    'Лизинг': 'leasing',
    'Участие в проекте': 'project',
    'Обмен': 'barter',
    'Безвозмездно': 'free',
}


def _category(env, cache, name, parent=None):
    """Категория или подкатегория по названию.

    Дерево двухуровневое, как в макете: «Продовольственные товары» →
    «Мясная и молочная продукция».
    """
    key = (name, parent.id if parent else False)
    if key in cache:
        return cache[key]
    domain = [('name', '=', name),
              ('parent_id', '=', parent.id if parent else False)]
    record = env['coop.resource.category'].search(domain, limit=1)
    if not record:
        record = env['coop.resource.category'].create({
            'name': name,
            'parent_id': parent.id if parent else False,
        })
    cache[key] = record
    return record


# Добор сверх макета. Решение владельца: опубликованных записей должно
# быть больше ста. После того как часть уйдёт в черновики по нехватке
# верификации у владельца, ста из ста не остаётся — значит записей нужно
# больше. Названия собираются из тех же категорий и городов, что в
# макете: «Ресурс №117» — это не пример, а заполнитель.
EXTRA_TITLES = [
    'Мотопомпа', 'Бетономешалка на 180 л', 'Леса строительные',
    'Сварочный полуавтомат', 'Дисковая пилорама', 'Сушильная камера',
    'Прицеп бортовой', 'Мотоблок с навесным', 'Косилка роторная',
    'Дровокол гидравлический', 'Пресс для сена', 'Ёмкость под воду',
    'Компрессор поршневой', 'Генератор на 5 кВт', 'Плуг оборотный',
    'Опрыскиватель прицепной', 'Зернодробилка', 'Инкубатор на 500 яиц',
    'Медогонка на 8 рамок', 'Морозильный ларь',
]


def _extra_rows(rows, extra):
    cities = sorted({row['city'] for row in rows if row.get('city')})
    extras = []
    for i in range(extra):
        source = rows[(i * 11) % len(rows)]
        city = cities[(i * 5) % len(cities)] if cities else ''
        row = dict(source)
        row['name'] = '%s — %s' % (EXTRA_TITLES[i % len(EXTRA_TITLES)], city)
        row['city'] = city
        row['promoted'] = False
        extras.append(row)
    return extras


def load_resources(env, extra=45):
    with open(os.path.join(HERE, 'resources.json'), encoding='utf-8') as fh:
        rows = json.load(fh)
    rows = rows + _extra_rows(rows, extra)

    methods = {m.code: m for m in env['coop.resource.method'].search([])}
    Resource = env['coop.resource']
    Partner = env['res.partner']

    # Участники, между которыми раздаются объявления без владельца.
    # Организации идут первыми: у ресурса чаще стоит юридическое лицо, и
    # каталог, где всё принадлежит частным лицам, выглядел бы неправдой.
    owners = Partner.search([('coop_is_participant', '=', True)], order='is_company desc, id')
    if not owners:
        _logger.warning('Нет участников — ресурсы загружать не на кого')
        return

    categories = {}
    created = updated = 0

    for index, row in enumerate(rows):
        parent = _category(env, categories, row['category']) if row['category'] else None
        category = (_category(env, categories, row['subcategory'], parent)
                    if row['subcategory'] else parent)

        method_codes = [METHODS[m] for m in row['methods'] if m in METHODS]
        method_ids = [methods[c].id for c in method_codes if c in methods]

        # Владелец: указанный в макете, иначе — по кругу из каталога.
        owner = None
        if row['owner']:
            owner = Partner.search([('name', '=', row['owner'])], limit=1)
        if not owner:
            owner = owners[index % len(owners)]

        values = {
            'name': row['name'],
            'listing_type': 'request' if row['listing'] == 'Спрос' else 'offer',
            'resource_type': TYPES.get(row['type'], 'material'),
            'category_id': category.id if category else False,
            'method_ids': [(6, 0, method_ids)],
            'owner_id': owner.id,
            'city': row['city'],
            'price': row['price'],
            'price_kind': row['price_kind'],
            'price_unit_label': row['price_unit'],
            'state': 'published',
        }

        photo = os.path.join(PHOTO_DIR, os.path.basename(row['image'])) if row['image'] else ''
        if photo and os.path.exists(photo):
            with open(photo, 'rb') as fh:
                values['image_1920'] = base64.b64encode(fh.read())

        # Ключ — название вместе с городом и владельцем: в макете
        # одинаковые названия встречаются у разных участников («Сварочный
        # аппарат» и в предложении, и в спросе), и схлопывать их нельзя.
        existing = Resource.search([
            ('name', '=', row['name']),
            ('city', '=', row['city']),
            ('owner_id', '=', owner.id),
        ], limit=1)
        if existing:
            existing.write(values)
            updated += 1
        else:
            Resource.create(values)
            created += 1

    _logger.info('Каталог ресурсов: %s записей, создано %s, обновлено %s, '
                 'категорий %s', len(rows), created, updated, len(categories))
