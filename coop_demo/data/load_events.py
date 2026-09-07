# -*- coding: utf-8 -*-
"""Календарь кооперативной жизни: одиннадцать событий макета и добор.

Одиннадцать событий взяты из макета как есть — вместе с датами,
значками и числом записавшихся. Добор идёт теми же видами по городам и
месяцам: собрания пайщиков проходят раз в год у каждого кооператива,
ярмарки — по сезону, созвоны — еженедельно, и это не выдумка ради
объёма, а обычный ритм.

Прошедшие события показаны наравне с будущими. Календарь, в котором
видно только предстоящее, не даёт понять, живёт ли платформа: по
прошедшим встречам это как раз видно.
"""
import io
import json
import logging
import os
import random
from datetime import datetime, timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

CATEGORY = {
    'Собрания пайщиков': 'meeting',
    'Обучение': 'learning',
    'Праздники и ярмарки': 'fair',
    'Мероприятия сообществ': 'community',
    'Встречи и знакомства': 'meetup',
}

FORMAT = {'Офлайн': 'offline', 'Онлайн': 'online', 'Смешанный': 'mixed'}

# Что проводят чаще всего — по видам. Названия из тех же кооперативных
# практик, что и в макете: отчётное собрание, сезонная ярмарка, разбор
# устава, обучение переработке.
TITLES = {
    'meeting': [
        'Отчётное собрание пайщиков',
        'Внеочередное собрание: приём новых пайщиков',
        'Утверждение сметы на год',
        'Отчёт ревизионной комиссии',
    ],
    'learning': [
        'Мастер-класс по переработке молока',
        'Школа кооператора: устав и паевые взносы',
        'Практикум по хранению овощей',
        'Разбор кооперативного учёта на примерах',
        'Курс по пчеловодству для начинающих',
    ],
    'fair': [
        'Ярмарка кооперативных продуктов',
        'Осенний фермерский рынок',
        'Праздник урожая',
        'Медовая ярмарка',
    ],
    'community': [
        'Созвон сообщества: разбор вопросов',
        'Субботник на общей площадке',
        'Встреча пасечников',
        'Общий сбор соседей',
    ],
    'meetup': [
        'Знакомство новых участников',
        'Кооперативный завтрак',
        'Встреча по обмену семенами',
        'Вечер обмена навыками',
    ],
}

ICONS = {'meeting': '🗳️', 'learning': '📚', 'fair': '🎉',
         'community': '🏘️', 'meetup': '🤝'}

PLACES = [
    'зал правления кооператива',
    'площадка у склада, ул. Заводская, 14',
    'дом культуры, малый зал',
    'открытая площадка у рынка',
    'ссылка на созвон придёт записавшимся',
]

TARGET = 140


def load_events(env, target=TARGET):
    Event = env['coop.event'].sudo()
    Signup = env['coop.event.signup'].sudo()
    Partner = env['res.partner'].sudo()

    if Event.search_count([]) >= target // 2:
        _logger.info('События: уже наполнены, пропускаю')
        return

    companies = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)],
        order='id')
    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)],
        order='id')
    if not companies or not people:
        _logger.warning('Нет участников — события не наполняю')
        return

    communities = env['coop.community'].sudo().search([]) \
        if 'coop.community' in env else env['res.partner'].browse()
    cities = sorted({p.city for p in companies if p.city}) or ['Москва']
    showcase = env['res.users'].sudo().search([('login', '=', 'dashkevich')], limit=1)
    me = showcase.partner_id
    pool = [pid for pid in people.ids if pid != me.id]

    with io.open(os.path.join(HERE, 'events.json'), encoding='utf-8') as fh:
        rows = json.load(fh)

    rnd = random.Random(20260907)
    now = fields.Datetime.now()
    created = 0

    # ── Из макета, как есть ──────────────────────────────────────────────
    for row in rows:
        category = CATEGORY.get(row['category'], 'meetup')
        date = datetime.strptime(row['date'], '%Y-%m-%d').replace(
            hour=rnd.choice([10, 12, 15, 18, 21]))
        event = Event.create({
            'name': row['title'],
            'icon': row['icon'] or ICONS[category],
            'category': category,
            'format': FORMAT.get(row['format'], 'offline'),
            'organizer_id': companies[created % len(companies)].id,
            'city': row['city'],
            'place': rnd.choice(PLACES),
            'date_start': date,
            'date_end': date + timedelta(hours=rnd.choice([2, 3, 5, 7])),
            'description': '<p>%s</p>' % row['text'],
            'capacity': rnd.choice([0, 0, 30, 50, 80]),
            'state': 'held' if date < now else 'open',
        })
        _sign_people(Signup, event, pool, int(row['people'] or 20), rnd, now)
        created += 1

    # ── Добор по городам и месяцам ───────────────────────────────────────
    while created < target:
        category = list(TITLES)[created % len(TITLES)]
        city = cities[created % len(cities)]
        title = TITLES[category][created % len(TITLES[category])]
        # Год с небольшим назад и полгода вперёд: календарь должен
        # показывать и то, что было, и то, что будет.
        date = (now + timedelta(days=rnd.randint(-400, 180))).replace(
            hour=rnd.choice([10, 12, 15, 18, 21]), minute=0, second=0,
            microsecond=0)
        event = Event.create({
            'name': '%s — %s' % (title, city),
            'icon': ICONS[category],
            'category': category,
            'format': rnd.choice(['offline'] * 4 + ['online'] * 2 + ['mixed']),
            'organizer_id': companies[created % len(companies)].id,
            'community_id': (communities[created % len(communities)].id
                             if communities and category == 'community' else False),
            'city': city,
            'place': rnd.choice(PLACES),
            'date_start': date,
            'date_end': date + timedelta(hours=rnd.choice([2, 3, 5])),
            'description': '<p>Событие кооперативной жизни: %s.</p>' % title.lower(),
            'capacity': rnd.choice([0, 0, 25, 40, 60, 120]),
            'state': ('held' if date < now
                      else rnd.choice(['open'] * 5 + ['draft'] + ['cancelled'])),
        })
        _sign_people(Signup, event, pool, rnd.randint(5, 70), rnd, now)
        created += 1

    _showcase(env, rnd, me)
    _logger.info('События: создано %s', created)


def _sign_people(Signup, event, pool, wanted, rnd, now):
    """Записать людей на событие.

    У прошедших событий часть записей закрывается отметками «был» и «не
    пришёл»: разрыв между записавшимися и пришедшими — обычное дело, и
    организатор должен видеть его в данных, а не узнавать на месте.
    """
    wanted = max(1, min(wanted, len(pool)))
    if event.capacity:
        wanted = min(wanted, event.capacity)
    for partner_id in rnd.sample(pool, wanted):
        if event.date_start < now:
            state = rnd.choice(['attended'] * 6 + ['missed'] * 2 + ['cancelled'])
        else:
            state = rnd.choice(['going'] * 9 + ['cancelled'])
        Signup.create({'event_id': event.id, 'partner_id': partner_id,
                       'state': state})


def _showcase(env, rnd, me):
    """Участник показа записан на несколько событий, в том числе будущих."""
    if not me:
        return
    Event = env['coop.event'].sudo()
    Signup = env['coop.event.signup'].sudo()
    upcoming = Event.search([('date_start', '>', fields.Datetime.now())])
    past = Event.search([('date_start', '<=', fields.Datetime.now())])
    for event in rnd.sample(list(upcoming), min(5, len(upcoming))):
        if not Signup.search_count([('event_id', '=', event.id),
                                    ('partner_id', '=', me.id)]):
            Signup.create({'event_id': event.id, 'partner_id': me.id,
                           'state': 'going'})
    for event in rnd.sample(list(past), min(7, len(past))):
        if not Signup.search_count([('event_id', '=', event.id),
                                    ('partner_id', '=', me.id)]):
            Signup.create({'event_id': event.id, 'partner_id': me.id,
                           'state': 'attended'})
