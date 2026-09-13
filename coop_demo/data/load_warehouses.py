# -*- coding: utf-8 -*-
"""Склады участников и биржа свободных мощностей.

Склад берётся не из головы: у кооператива он почти всегда привязан к
тому, что кооператив делает. У молочного — холодильная камера, у
зернового — ангар и открытая площадка под технику, у ягодного —
морозильник, который девять месяцев в году стоит пустым. Поэтому тип
хранения, единица учёта, размер и цена выводятся из одного и того же
набора правил, а не подставляются по отдельности: иначе получается
морозильная камера, считающая место квадратными метрами, и аренда
паллетоместа по цене открытой площадки.

Занятость собирается из трёх частей и ни одна не выдумана отдельно:
своё — доля от ёмкости, сданное другим — сумма действующих сделок,
свободное — остаток. Свободное и выставляется на биржу, поэтому
объявления никогда не обещают больше, чем на складе есть.

На бирже две стороны. «Предлагают» — всегда от конкретного склада.
«Ищут» — потребность без склада, и таких примерно треть: биржа, где
все только предлагают, показывает рынок неправдиво.
"""
import logging
import random
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

# Тип хранения → единица учёта, границы ёмкости, цена аренды за единицу
# в месяц. Цены — порядок величины по рынку складов в областных центрах:
# сухой неотапливаемый дешевле отапливаемого вдвое, морозильник дороже
# холодильника, открытая площадка дешевле всего.
KINDS = {
    'dry_heated': ('sqm', 200, 1600, 380, 700),
    'dry_cold': ('sqm', 150, 2200, 170, 340),
    'chilled': ('pallet', 20, 220, 900, 1500),
    'frozen': ('pallet', 20, 260, 1250, 2300),
    'open': ('sqm', 400, 5000, 55, 140),
}

# Названия складов — по типу хранения. Ни одно название не подходит
# двум типам сразу: «морозильная камера» не может оказаться открытой
# площадкой, даже если строку взяли по ошибке.
NAMES = {
    'dry_heated': [
        'Сухой отапливаемый склад на Заводской',
        'Отапливаемый склад при цехе',
        'Тёплый склад готовой продукции',
        'Склад с отоплением в промзоне',
        'Отапливаемый ангар под фасовку',
        'Тёплый склад при магазине',
        'Отапливаемое хранилище семян',
        'Склад с подогревом у трассы',
    ],
    'dry_cold': [
        'Холодный ангар на окраине',
        'Неотапливаемый склад у железной дороги',
        'Сухой ангар под инвентарь',
        'Складской бокс без отопления',
        'Ангар под тару и упаковку',
        'Холодный склад при пилораме',
        'Ангар за мехмастерской',
        'Бокс у зернотока',
    ],
    'chilled': [
        'Холодильная камера при молочном цехе',
        'Холодильник для овощей и зелени',
        'Камера +2…+6 при производстве',
        'Холодильная камера на базе',
        'Холодильник под фрукты',
        'Камера охлаждения при бойне',
        'Холодильник овощехранилища',
        'Камера при рыбном участке',
    ],
    'frozen': [
        'Морозильная камера −18 при цехе',
        'Морозильник под ягоду',
        'Низкотемпературная камера на базе',
        'Морозильная камера рыбного цеха',
        'Морозильник для полуфабрикатов',
        'Морозильная камера мясного цеха',
        'Камера −18 при овощебазе',
        'Морозильник под грибы',
    ],
    'open': [
        'Открытая площадка у элеватора',
        'Площадка под технику за городом',
        'Открытое хранение стройматериалов',
        'Асфальтированная площадка на выезде',
        'Площадка под пиломатериалы',
        'Открытая площадка при мехдворе',
        'Площадка у зернотока',
        'Открытое хранение поддонов',
    ],
}

ADDRESSES = [
    'ул. Заводская, 14', 'ул. Промышленная, 3, корпус 2',
    'Северный проезд, 7', 'ул. Элеваторная, 21',
    'Тракт на объездной, 4 км', 'ул. Складская, 9',
    'пер. Транспортный, 5', 'ул. Базовая, 16, ворота 3',
]

SCHEDULES = [
    'Пн–Пт, 9:00–18:00',
    'Пн–Сб, 8:00–20:00',
    'Ежедневно, 7:00–22:00',
    'Круглосуточно, по звонку',
    'Пн–Пт, 8:00–17:00, обед 12:00–13:00',
]

ZONES = {
    'dry_heated': [('Стеллажная зона', 'rent'), ('Зона фасовки', None),
                   ('Приёмка', None)],
    'dry_cold': [('Ближний бокс', 'rent'), ('Дальний бокс', 'custody'),
                 ('Навес', None)],
    'chilled': [('Камера №1', 'rent'), ('Камера №2', 'custody')],
    'frozen': [('Камера А', 'rent'), ('Камера Б', 'project'),
               ('Шоковая заморозка', None)],
    'open': [('Асфальт, восточная часть', 'rent'),
             ('Грунтовая часть', 'barter'), ('Под навесом', None)],
}

# Чего ищут те, у кого склада нет. Тип хранения назван в самой
# потребности, поэтому запрос на морозильник не может уехать в сухой
# ангар: и то и другое берётся из одной строки.
REQUESTS = [
    ('Нужен морозильник под ягоду на сезон', 'frozen', 20, 60),
    ('Ищем морозильную камеру для полуфабрикатов', 'frozen', 15, 50),
    ('Нужна камера −18 на три месяца', 'frozen', 10, 40),
    ('Ищем холодильник под овощи до весны', 'chilled', 20, 80),
    ('Нужна камера +2…+6 под молочное', 'chilled', 10, 45),
    ('Ищем холодильную камеру под зелень', 'chilled', 8, 30),
    ('Нужен сухой отапливаемый склад под фасовку', 'dry_heated', 80, 400),
    ('Ищем тёплый склад под готовую продукцию', 'dry_heated', 100, 500),
    ('Нужен отапливаемый угол под сушку трав', 'dry_heated', 40, 150),
    ('Ищем холодный ангар под инвентарь', 'dry_cold', 100, 600),
    ('Нужен ангар под тару на зиму', 'dry_cold', 80, 400),
    ('Ищем неотапливаемый бокс под запчасти', 'dry_cold', 50, 250),
    ('Нужна площадка под технику на межсезонье', 'open', 300, 1500),
    ('Ищем открытое хранение пиломатериалов', 'open', 200, 1000),
    ('Нужна площадка под стройматериалы', 'open', 150, 800),
]

# Что ещё пишут в объявлении, кроме цены. Оговорки настоящие: по ним
# видно, что место обсуждали, а не просто выложили.
NOTES = [
    'приёмка только в рабочие часы',
    'погрузчик наш, работает грузчик склада',
    'въезд фурам ограничен, только до 5 тонн',
    'минимальный срок — месяц',
    'оплата помесячно, вперёд',
    'пандус, разгрузка с борта',
    'страхование за счёт размещающего',
    'своя охрана и видеонаблюдение',
]

TARGET_WAREHOUSES = 115
TARGET_OFFERS = 165


def load_warehouses(env, warehouses=TARGET_WAREHOUSES, offers=TARGET_OFFERS):
    Warehouse = env['coop.warehouse'].sudo()
    Zone = env['coop.warehouse.zone'].sudo()
    Offer = env['coop.warehouse.offer'].sudo()
    Term = env['coop.warehouse.offer.term'].sudo()
    Deal = env['coop.deal'].sudo()
    Partner = env['res.partner'].sudo()

    if Warehouse.search_count([]) >= warehouses // 2:
        _logger.info('Склады: уже наполнены, пропускаю')
        return

    companies = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)],
        order='id')
    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)],
        order='id')
    if not companies or not people:
        _logger.warning('Нет участников — склады не наполняю')
        return

    rnd = random.Random(20260913)
    today = fields.Date.today()
    kinds = list(KINDS)
    made_warehouses = []

    for index in range(warehouses):
        # Склад чаще у организации: у частника склад — редкость, и
        # каталог, где склады поровну, показывает не тот рынок.
        owner = (companies[index % len(companies)] if index % 5 != 4
                 else people[(index * 3) % len(people)])
        kind = kinds[index % len(kinds)]
        unit, low, high, rent_low, rent_high = KINDS[kind]
        capacity = float(rnd.randrange(low, high, 10))
        name = '%s, %s' % (NAMES[kind][(index // len(kinds)) % len(NAMES[kind])],
                           owner.city or 'город не указан')

        with env.cr.savepoint():
            warehouse = Warehouse.create({
                'name': name,
                'owner_id': owner.id,
                'keeper_id': people[(index * 11) % len(people)].id
                             if index % 3 == 0 else False,
                'city': owner.city or 'Москва',
                'address': ADDRESSES[index % len(ADDRESSES)],
                'schedule': SCHEDULES[index % len(SCHEDULES)],
                'storage_kind': kind,
                'capacity_unit': unit,
                'capacity': capacity,
                # Под своё уходит от трети до половины: склад, забитый
                # своим под потолок, на бирже никому не интересен, а
                # пустой на три четверти выглядит выдумкой.
                'used_own': round(capacity * rnd.uniform(0.30, 0.50), 1),
            })
            for order, (zone_name, terms) in enumerate(ZONES[kind]):
                Zone.create({
                    'warehouse_id': warehouse.id,
                    'sequence': (order + 1) * 10,
                    'name': zone_name,
                    'capacity': round(capacity / (len(ZONES[kind]) + 1), 1),
                    'terms': terms,
                    'note': NOTES[(index + order) % len(NOTES)]
                            if order == 0 else False,
                })
            made_warehouses.append((warehouse, rent_low, rent_high))

    _logger.info('Складов создано: %s', len(made_warehouses))

    # ── Сделки: часть места уже сдана ───────────────────────────────────
    #
    # Без них на всех складах свободно ровно столько, сколько не занято
    # своим, и полоса занятости выходит двухцветной у семидесяти складов
    # подряд. Сдают не все и не всё: две трети складов вовсе без сделок.
    deal_states = ['active', 'active', 'agreed', 'acceptance', 'done',
                   'cancelled']
    deals_made = 0
    for index, (warehouse, rent_low, rent_high) in enumerate(made_warehouses):
        if index % 3 == 0:
            continue
        free = warehouse.capacity - warehouse.used_own
        for step in range(rnd.randint(1, 2)):
            volume = round(free * rnd.uniform(0.10, 0.25), 1)
            if volume <= 0:
                continue
            counterparty = (companies[(index * 7 + step) % len(companies)]
                            if step == 0
                            else people[(index * 5 + step) % len(people)])
            if counterparty == warehouse.owner_id:
                continue
            state = deal_states[(index + step) % len(deal_states)]
            terms = ['rent', 'custody', 'project', 'barter'][(index + step) % 4]
            price = rnd.randrange(rent_low, rent_high, 10)
            with env.cr.savepoint():
                Deal.create({
                    'name': 'Складское место: %s' % warehouse.name,
                    'subject': 'resource',
                    'way': 'rent' if terms in ('rent', 'custody') else (
                        'exchange' if terms == 'barter' else 'share'),
                    'party_a_id': warehouse.owner_id.id,
                    'party_b_id': counterparty.id,
                    'role_a': 'владелец склада',
                    'role_b': 'размещающий',
                    'city': warehouse.city,
                    'amount': (price * volume
                               if terms in ('rent', 'custody') else 0),
                    'signed_on': today - timedelta(days=rnd.randint(10, 400)),
                    'state': state,
                    'warehouse_id': warehouse.id,
                    'warehouse_volume': volume,
                    'warehouse_terms': terms,
                })
                deals_made += 1

    _logger.info('Договорённостей по складам: %s', deals_made)

    # ── Биржа: предложения от складов ───────────────────────────────────
    #
    # Объём предложения режется по свободному остатку: обещать место,
    # которого нет, — ровно то, из-за чего биржами перестают
    # пользоваться.
    offer_states = ['published'] * 7 + ['matched', 'closed', 'draft']
    made_offers = 0
    for index, (warehouse, rent_low, rent_high) in enumerate(made_warehouses):
        if made_offers >= offers * 2 // 3:
            break
        warehouse.invalidate_recordset(['used_rented', 'free'])
        free = warehouse.free
        if free <= 0:
            continue
        for step in range(rnd.randint(1, 2)):
            volume = round(free * rnd.uniform(0.4, 0.9), 1)
            if volume <= 0:
                continue
            state = offer_states[(index + step) % len(offer_states)]
            start = today + timedelta(days=rnd.randint(-60, 30))
            with env.cr.savepoint():
                offer = Offer.create({
                    'name': warehouse.name,
                    'side': 'offer',
                    'owner_id': warehouse.owner_id.id,
                    'warehouse_id': warehouse.id,
                    'city': warehouse.city,
                    'storage_kind': warehouse.storage_kind,
                    'volume': volume,
                    'capacity_unit': warehouse.capacity_unit,
                    'date_from': start,
                    'date_to': start + timedelta(days=rnd.choice(
                        [90, 120, 180, 365])),
                    'state': state,
                    'published_on': (start if state != 'draft' else False),
                    'contact_note': NOTES[(index + step) % len(NOTES)],
                })
                _make_terms(Term, offer, rnd, rent_low, rent_high,
                            warehouse.capacity_unit)
                made_offers += 1

    # ── Биржа: запросы без склада ───────────────────────────────────────
    for index in range(offers - made_offers):
        title, kind, low, high = REQUESTS[index % len(REQUESTS)]
        unit, _low, _high, rent_low, rent_high = KINDS[kind]
        seeker = (people[(index * 13) % len(people)] if index % 3
                  else companies[(index * 9) % len(companies)])
        start = today + timedelta(days=rnd.randint(-30, 45))
        with env.cr.savepoint():
            offer = Offer.create({
                'name': title,
                'side': 'request',
                'owner_id': seeker.id,
                'city': seeker.city or 'Москва',
                'storage_kind': kind,
                'volume': float(rnd.randrange(low, high, 5)),
                'capacity_unit': unit,
                'date_from': start,
                'date_to': start + timedelta(days=rnd.choice([60, 90, 180])),
                'state': 'published' if index % 8 else 'closed',
                'published_on': start,
                'contact_note': NOTES[index % len(NOTES)],
            })
            _make_terms(Term, offer, rnd, rent_low, rent_high, unit,
                        seeking=True)
            made_offers += 1

    _logger.info('Объявлений на бирже: %s', made_offers)


def _make_terms(Term, offer, rnd, rent_low, rent_high, unit, seeking=False):
    """Условия объявления: от одного до четырёх, и цена только у денежных.

    Набор условий не случаен. Аренда есть почти всегда — это то, что
    понимают все. Участие в проекте, пай и обмен добавляются реже: они
    и есть кооперативная часть биржи, но объявление, где предлагают
    только их, читается как экзотика.
    """
    per = {'sqm': 'за м² в месяц', 'pallet': 'за паллетоместо в месяц',
           'ton': 'за тонну в месяц'}[unit]
    price = rnd.randrange(rent_low, rent_high, 10)

    rows = [('rent', price, per)]
    if rnd.random() < 0.45:
        # Ответственное хранение дороже аренды: владелец принимает,
        # считает и отгружает, а это работа, а не только место.
        rows.append(('custody', round(price * rnd.uniform(1.3, 1.7) / 10) * 10,
                     per))
    if rnd.random() < 0.30:
        rows.append(('project', 0, False))
    if rnd.random() < 0.22:
        rows.append(('barter', 0, False))
    if rnd.random() < 0.15:
        rows.append(('share', 0, False))
    if rnd.random() < 0.10:
        rows.append(('buyout', price * rnd.randrange(18, 36), 'за единицу'))

    if seeking:
        # Ищущий не назначает цену за хранение, он готов её платить:
        # выкупа и пая в запросе не бывает.
        rows = [row for row in rows if row[0] not in ('buyout', 'share')]

    notes = ['срок от месяца', 'оплата помесячно', 'с актом приёма-передачи',
             'страхование обсуждается', False, False]
    for order, (kind, value, price_unit) in enumerate(rows):
        Term.create({
            'offer_id': offer.id,
            'sequence': (order + 1) * 10,
            'kind': kind,
            'price': value or 0,
            'price_unit': price_unit or False,
            'note': notes[(offer.id + order) % len(notes)],
        })
