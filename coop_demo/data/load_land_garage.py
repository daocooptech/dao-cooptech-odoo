# -*- coding: utf-8 -*-
"""Земельные участки, гаражи и машиноместа (задача 398, 10.11.2026).

После перестройки дерева в «Земельных участках» лежало одно объявление,
а у гаражей были только однотипные «ищу место под хранение мотоцикла».
Образцы (Авито, OLX) делят землю по назначению — ИЖС, садоводство,
сельхоз, промышленность — и показывают площадь в сотках и гектарах, а
гараж — по виду (капитальный, металлический, машиноместо) и площади.
Здесь недостающие объявления и значения этих характеристик.

Идемпотентно: запись узнаётся по названию, городу и рубрике.
"""
import logging
import random

_logger = logging.getLogger(__name__)

# (название, город, способ, цена, единица, назначение/вид, площадь)
LAND = [
    ('Участок под ИЖС 10 соток, газ по границе', 'Краснодар', 'sale', 2400000, '', 'izhs', 10),
    ('Участок 12 соток, свет и вода, рядом лес', 'Тюмень', 'sale', 1350000, '', 'izhs', 12),
    ('Садовый участок 6 соток с домиком', 'Пермь', 'sale', 480000, '', 'sadovodstvo_snt', 6),
    ('Участок в СНТ, 8 соток, членские взносы оплачены', 'Челябинск', 'sale', 390000, '', 'sadovodstvo_snt', 8),
    ('Земля сельхозназначения 12 га, пашня', 'Омск', 'sale', 1800000, '', 'selhoznaznacheniya', 1200),
    ('Сдам поле под посев на сезон, 30 га', 'Ростов-на-Дону', 'rent', 4500, 'га/сезон', 'selhoznaznacheniya', 3000),
    ('Участок под пасеку, 25 соток у леса', 'Алтайский край', 'sale', 210000, '', 'selhoznaznacheniya', 25),
    ('Участок под склад, промзона, 40 соток', 'Новосибирск', 'sale', 6200000, '', 'promyshlennogo_naznacheniya', 40),
    ('Площадка под производство 1,2 га, подъездные пути', 'Красноярск', 'rent', 95000, 'мес', 'promyshlennogo_naznacheniya', 120),
    ('Участок ЛПХ 15 соток, колодец', 'Воронеж', 'sale', 760000, '', 'lph', 15),
    ('Ищу участок под теплицы до 20 соток', 'Нижний Новгород', 'sale', 0, '', 'selhoznaznacheniya', 20),
    ('Участок у воды, 9 соток, можно под базу отдыха', 'Архангельск', 'sale', 890000, '', 'rekreacionnogo_naznacheniya', 9),
    ('Обменяю участок 6 соток на инструмент и материалы', 'Казань', 'barter', 0, '', 'sadovodstvo_snt', 6),
    ('Участок 20 соток, под малую ферму', 'Екатеринбург', 'sale', 1150000, '', 'lph', 20),
]

GARAGES = [
    ('Капитальный гараж 24 м², яма, свет', 'Москва', 'sale', 1250000, '', 'kapitalnyy_garazh', 24),
    ('Металлический гараж-ракушка, вывоз за счёт покупателя', 'Пермь', 'sale', 45000, '', 'metallicheskiy_garazh', 15),
    ('Машиноместо в подземном паркинге', 'Санкт-Петербург', 'sale', 1800000, '', 'mashinomesto_v_parkinge', 13),
    ('Сдам машиноместо в охраняемом дворе', 'Екатеринбург', 'rent', 4500, 'мес', 'mashinomesto_na_otkrytoy_stoyanke', 12),
    ('Сдам гараж под мастерскую, 36 м², отопление', 'Новосибирск', 'rent', 9000, 'мес', 'kapitalnyy_garazh', 36),
    ('Гараж-бокс в кооперативе, документы в порядке', 'Челябинск', 'sale', 380000, '', 'kapitalnyy_garazh', 21),
    ('Ищу машиноместо рядом с метро', 'Москва', 'rent', 0, '', 'mashinomesto_v_parkinge', 13),
    ('Сдам место под хранение лодки и прицепа', 'Тюмень', 'rent', 3000, 'мес', 'mashinomesto_na_otkrytoy_stoyanke', 25),
]


def load_land_garage(env):
    """Завести земельные участки и гаражи; вернуть, сколько создано."""
    Resource = env['coop.resource'].sudo()
    Category = env['coop.resource.category'].sudo()
    methods = {m.code: m for m in
               env['coop.resource.method'].sudo().search([])}
    owners = env['res.partner'].sudo().search(
        [('coop_is_participant', '=', True)], order='is_company desc, id')
    land = Category.search([('name', '=', 'Земельные участки')], limit=1)
    garage = Category.search([('name', '=', 'Гаражи и машиноместа')], limit=1)
    if not (owners and land and garage):
        _logger.info('Земля и гаражи: нет владельцев или рубрик — пропуск')
        return 0
    rnd = random.Random(20261110)
    created = 0
    for category, rows, kind_key, area_key in (
            (land, LAND, 'land_category', 'land_sotka'),
            (garage, GARAGES, 'garage_kind', 'garage_area_m2')):
        for name, city, method, price, unit, kind, area in rows:
            owner = owners[rnd.randrange(len(owners))]
            if Resource.search_count([('name', '=', name), ('city', '=', city),
                                      ('category_id', '=', category.id)]):
                continue
            wanted = name.startswith(('Ищу', 'Нужен'))
            Resource.create({
                'name': name,
                'listing_type': 'request' if wanted else 'offer',
                'resource_type': 'material',
                'category_id': category.id,
                'method_ids': [(6, 0, [methods[method].id])]
                if method in methods else False,
                'owner_id': owner.id,
                'city': city,
                'price': price,
                'price_kind': 'exact' if price else 'none',
                'price_unit_label': unit,
                'state': 'published',
                'attrs': {kind_key: kind, area_key: area},
            })
            created += 1
    _logger.info('Земля и гаражи: создано %s', created)
    return created
