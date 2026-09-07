# -*- coding: utf-8 -*-
"""Аукционы: то, что кооперативы действительно разыгрывают.

Лоты двух родов. На повышение уходит то, что у хозяйства лишнее:
подержанная техника, партия урожая, место на складе. Редукционом ищут
исполнителя — вспашку, ремонт кровли, вывоз зерна.

Торги показаны на всех стадиях, включая несостоявшиеся. Аукцион, где
всегда есть победитель, вводит в заблуждение: половина лотов уходит без
ставок или не добирает до резервной цены, и участник должен видеть это
в каталоге, а не узнавать на своём лоте.
"""
import logging
import random
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

# Лот, вид торга, стартовая цена, шаг.
LOTS = [
    ('Трактор МТЗ-82, 2014 год, наработка 6200 моточасов', 'direct', 780000, 10000),
    ('Прицеп тракторный 2ПТС-4,5 после ремонта', 'direct', 165000, 5000),
    ('Партия картофеля «Гала», 12 тонн', 'direct', 210000, 3000),
    ('Зерносушилка передвижная', 'direct', 340000, 10000),
    ('Место на складе, 60 м² на сезон', 'direct', 48000, 2000),
    ('Пресс-подборщик рулонный', 'direct', 295000, 5000),
    ('Партия мёда разнотравье, 400 кг', 'direct', 176000, 4000),
    ('Доильный аппарат на 2 головы', 'direct', 54000, 2000),
    ('Вспашка 40 га под зябь', 'reverse', 160000, 5000),
    ('Ремонт кровли склада, 300 м²', 'reverse', 420000, 10000),
    ('Вывоз зерна с поля, 200 тонн', 'reverse', 95000, 3000),
    ('Монтаж системы полива на 3 га', 'reverse', 380000, 10000),
    ('Ветеринарное обслуживание стада на год', 'reverse', 240000, 8000),
    ('Разработка сайта кооператива', 'reverse', 180000, 5000),
    ('Бухгалтерское сопровождение, год', 'reverse', 144000, 4000),
]

TARGET = 105


def load_auctions(env, target=TARGET):
    Auction = env['coop.auction'].sudo()
    Bid = env['coop.auction.bid'].sudo()
    Partner = env['res.partner'].sudo()

    if Auction.search_count([]) >= target // 2:
        _logger.info('Аукционы: уже наполнены, пропускаю')
        return

    companies = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)],
        order='id')
    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)],
        order='id')
    if not companies or not people:
        _logger.warning('Нет участников — аукционы не наполняю')
        return

    cities = sorted({p.city for p in companies if p.city}) or ['Москва']
    rnd = random.Random(20260907)
    now = fields.Datetime.now()
    created = 0

    for index in range(target):
        title, kind, start, step = LOTS[index % len(LOTS)]
        city = cities[index % len(cities)]
        owner = companies[index % len(companies)]

        # Время окончания задаёт состояние: будущие идут, прошедшие уже
        # чем-то кончились. Часть идущих кончается в ближайший час — на
        # них видно подсветку «осталось меньше часа».
        offset_hours = rnd.choice(
            [rnd.randint(1, 3)] * 2 + [rnd.randint(6, 240)] * 5
            + [-rnd.randint(2, 2000)] * 8)
        date_end = now + timedelta(hours=offset_hours)
        date_start = date_end - timedelta(days=rnd.randint(3, 14))

        auction = Auction.create({
            'name': title if index < len(LOTS) else '%s — %s' % (title, city),
            'kind': kind,
            'owner_id': owner.id,
            'city': city,
            'start_price': start,
            'step': step,
            'reserve_price': (start * rnd.uniform(1.05, 1.4) if kind == 'direct'
                              else start * rnd.uniform(0.6, 0.9))
            if rnd.random() < 0.5 else 0.0,
            'date_start': date_start,
            'date_end': date_end,
            'extend_minutes': rnd.choice([0, 10, 10, 15, 30]),
            'description': '<p>Лот выставлен кооперативом. Осмотр по '
                           'договорённости, самовывоз.</p>',
            'state': 'running',
        })

        # Ставки: у части лотов их нет вовсе — это обычный исход, и он
        # должен встречаться в каталоге.
        bid_count = rnd.choice([0, 0, 1, 2, 3, 4, 5, 6, 8])
        bidders = rnd.sample(
            [pid for pid in people.ids], min(bid_count, len(people)))
        price = start
        for position, partner_id in enumerate(bidders):
            if kind == 'direct':
                price = price + step * rnd.randint(1, 3) if position else start
            else:
                price = price - step * rnd.randint(1, 3) if position else start
                if price <= step:
                    break
            Bid.create({'auction_id': auction.id, 'partner_id': partner_id,
                        'amount': price})

        if offset_hours < 0:
            auction.action_finish()
        created += 1

    _logger.info('Аукционы: создано %s', created)
