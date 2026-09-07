# -*- coding: utf-8 -*-
"""Совместные закупки: то, что кооперативы действительно берут вскладчину.

Товары взяты не с потолка: это позиции, ради которых складчина и
затевается — мешок дешевле фасовки, тонна дешевле мешка, а поодиночке
столько не нужно никому. Отсюда и объёмы: минимальный выкуп — это
реальная отгрузочная норма поставщика, а не круглое число.

Состояния разложены по срокам: часть закупок ещё собирает заказы, часть
уже раздана, а часть не состоялась — последнее важно показать. Складчина,
где всё всегда получается, вводит в заблуждение: не набрать объём —
обычный исход, и участник должен видеть его в каталоге.
"""
import logging
import random
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

# Товар, единица, минимальный выкуп, цена при минимуме, шаги удешевления.
GOODS = [
    ('Комбикорм для КРС, мешки по 25 кг', 'мешок', 40, 1180,
     [(80, 1090), (150, 1010), (300, 940)]),
    ('Сахар-песок, мешки по 50 кг', 'мешок', 20, 3400,
     [(50, 3220), (100, 3080)]),
    ('Мука пшеничная в/с, мешки по 50 кг', 'мешок', 30, 1850,
     [(60, 1740), (120, 1650)]),
    ('Дизельное топливо, литры', 'л', 2000, 68,
     [(5000, 65), (10000, 62)]),
    ('Семена картофеля «Гала», элита', 'кг', 500, 92,
     [(1500, 84), (3000, 78)]),
    ('Плёнка для теплиц, рулоны 3×100 м', 'рулон', 15, 8600,
     [(30, 8100), (60, 7600)]),
    ('Сетка-рабица оцинкованная, рулоны', 'рулон', 25, 3150,
     [(50, 2950), (100, 2790)]),
    ('Доска обрезная сухая, кубометры', 'м³', 12, 18500,
     [(30, 17200), (60, 16400)]),
    ('Цемент М500, мешки по 50 кг', 'мешок', 60, 640,
     [(150, 590), (300, 545)]),
    ('Удобрение аммиачная селитра, тонны', 'т', 5, 27400,
     [(15, 25800), (30, 24500)]),
    ('Банки стеклянные 3 л, паллета', 'шт.', 300, 78,
     [(900, 71), (1800, 66)]),
    ('Утеплитель минеральный, упаковки', 'уп.', 40, 1420,
     [(100, 1330), (200, 1250)]),
    ('Ящики для овощей, полипропилен', 'шт.', 200, 165,
     [(600, 148), (1200, 136)]),
    ('Сахарная свёкла на семена, мешки', 'мешок', 25, 2900,
     [(60, 2740), (120, 2600)]),
    ('Бензин АИ-92, литры', 'л', 3000, 58,
     [(8000, 56), (15000, 54)]),
]

PICKUP = [
    'склад кооператива, ул. Заводская, 14',
    'площадка у элеватора',
    'гараж на Северной, заезд со двора',
    'ангар на выезде из города',
    'общий склад программы',
]

TARGET = 120


def load_groupbuy(env, target=TARGET):
    Buy = env['coop.groupbuy'].sudo()
    Tier = env['coop.groupbuy.tier'].sudo()
    Order = env['coop.groupbuy.order'].sudo()
    Partner = env['res.partner'].sudo()

    if Buy.search_count([]) >= target // 2:
        _logger.info('Совместные закупки: уже наполнены, пропускаю')
        return

    companies = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)],
        order='id')
    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)],
        order='id')
    if not companies or not people:
        _logger.warning('Нет участников — закупки не наполняю')
        return

    cities = sorted({p.city for p in companies if p.city}) or ['Москва']
    showcase = env['res.users'].sudo().search([('login', '=', 'dashkevich')], limit=1)
    me = showcase.partner_id
    pool = [pid for pid in people.ids if pid != me.id]

    rnd = random.Random(20260907)
    today = fields.Date.context_today(Buy)
    created = 0

    for index in range(target):
        name, unit, min_volume, base, steps = GOODS[index % len(GOODS)]
        city = cities[index % len(cities)]
        organizer = companies[index % len(companies)]

        # Срок «стопа» задаёт состояние: будущие собирают, прошедшие уже
        # прошли свой путь. Так каталог сам собой выглядит живым, а не
        # набором записей в одном состоянии.
        offset = rnd.randint(-160, 25)
        stop_date = today + timedelta(days=offset)
        if offset > 0:
            state = 'collecting'
        else:
            state = rnd.choice(
                ['done'] * 5 + ['handout'] * 2 + ['delivering'] * 2
                + ['stopped'] + ['cancelled'] * 2)

        buy = Buy.create({
            'name': '%s — %s' % (name, city) if index >= len(GOODS) else name,
            'organizer_id': organizer.id,
            'supplier_name': rnd.choice([
                'ООО «Агроснаб»', 'Оптовая база №4', 'ТД «Зерновой»',
                'ИП Кузнецов', 'Комбинат «Северный»']),
            'city': city,
            'pickup_point': rnd.choice(PICKUP),
            'unit_label': unit,
            'min_volume': min_volume,
            'base_price': base,
            'org_fee_percent': rnd.choice([5.0, 7.0, 8.0, 10.0]),
            'stop_date': stop_date,
            'delivery_date': stop_date + timedelta(days=rnd.randint(5, 20)),
            'description': '<p>Закупка партией у поставщика. Оргсбор включён '
                           'в цену, доплачивать при снижении уровня не '
                           'нужно.</p>',
            'state': state,
        })
        for from_qty, price in steps:
            Tier.create({'groupbuy_id': buy.id, 'from_quantity': from_qty,
                         'price': price})

        # Набранный объём: у несостоявшихся — заведомо меньше минимума,
        # у остальных — от минимума и выше. Иначе «не состоялась» стоит
        # рядом с полной полосой набора и выглядит ошибкой.
        if state == 'cancelled':
            share = rnd.uniform(0.2, 0.85)
        else:
            share = rnd.uniform(1.0, 2.6)
        wanted = min_volume * share

        buyers = rnd.sample(pool, rnd.randint(4, min(18, len(pool))))
        # Каждая шестая закупка — с участием того, под кем ведётся показ:
        # без своих заказов вкладка «мои закупки» пуста.
        if me and index % 6 == 0:
            buyers.append(me.id)
        left = wanted
        for position, partner_id in enumerate(buyers):
            last = position == len(buyers) - 1
            quantity = round(left if last else wanted / len(buyers)
                             * rnd.uniform(0.5, 1.6), 2)
            quantity = max(min(quantity, left), 0.01)
            left = round(left - quantity, 2)
            Order.create({
                'groupbuy_id': buy.id,
                'partner_id': partner_id,
                'quantity': quantity,
                'state': {
                    'collecting': 'draft', 'cancelled': 'cancelled',
                    'done': 'taken', 'handout': 'confirmed',
                }.get(state, 'confirmed'),
            })
            if left <= 0:
                break
        created += 1

    _spread_created(env, rnd)
    _logger.info('Совместные закупки: создано %s', created)


def _spread_created(env, rnd):
    """Развести даты создания — каталог сортируется по сроку, но лента по ним."""
    for record_id in env['coop.groupbuy'].sudo().search([]).ids:
        env.cr.execute(
            "UPDATE coop_groupbuy SET create_date = now() - (%s || ' days')::interval "
            "WHERE id = %s", (rnd.randint(0, 200), record_id))
    env.invalidate_all()
