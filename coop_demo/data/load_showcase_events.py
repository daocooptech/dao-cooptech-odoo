# -*- coding: utf-8 -*-
"""Мероприятия витрины dashkevich — для штатного дашборда «События»
(решение 707, задача 494).

Организация проводит семинары, выезды и дни открытых дверей: шаблоны,
30 мероприятий за год и на два месяца вперёд, регистрации участников
площадки (подтверждены, пришли, отменены). Участникам организации —
доступ к мероприятиям (`event.group_event_user`).
Повторяемо: шаблон — по имени, мероприятие — по ключу
`coop_demo.evw_<орг>_<n>`.
"""
import logging
import random
from datetime import datetime, timedelta

from . import load_sales as ls

_logger = logging.getLogger(__name__)

KINDS = {
    'Семинар': ['Новые нормы ПУЭ: что изменилось', 'Учёт электроэнергии в МКД',
                'Энергоаудит предприятия', 'Частотные преобразователи на практике'],
    'Выезд на объект': ['Экскурсия на подстанцию 10 кВ', 'Монтаж вентиляции на складе',
                        'Сдача щитовой заказчику'],
    'День открытых дверей': ['День открытых дверей мастерской', 'Встреча с пайщиками'],
    'Обучение': ['Допуск по электробезопасности, III группа', 'Работа на высоте',
                 'Пусконаладка автоматики для новичков'],
}
EVENTS = 30


def load_showcase_events(env, login='dashkevich'):
    if 'event.event' not in env:
        return 0
    showcase = ls._showcase(env, login)
    people = env['res.partner'].sudo().search(
        [('coop_is_participant', '=', True), ('is_company', '=', False)], order='id')
    group = env.ref('event.group_event_user', raise_if_not_found=False)
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    made = 0
    for org in showcase:
        company = org.coop_company_id
        users = env['coop.membership'].sudo().search([
            ('organization_id', '=', org.id), ('state', '=', 'active'),
        ]).partner_id.user_ids.filtered(lambda u: not u.share and company in u.company_ids)
        if group:
            users.sudo().write({'group_ids': [(4, group.id)]})
        Type = env['event.type'].sudo()
        rnd = random.Random(20261130 + org.id)
        for number in range(EVENTS):
            xmlid = ls._key(env, 'evw', org, number)
            if ls._have(env, xmlid):
                continue
            kind = rnd.choice(list(KINDS))
            etype = Type.search([('name', '=', kind)], limit=1) or Type.create({'name': kind})
            begin = now + timedelta(days=rnd.randint(-330, 60), hours=rnd.choice((10, 11, 14, 15)) - now.hour)
            seats = rnd.choice((15, 20, 30, 50, 80))
            try:
                with env.cr.savepoint():
                    event = env['event.event'].sudo().with_company(company).create({
                        'name': rnd.choice(KINDS[kind]),
                        'event_type_id': etype.id,
                        'company_id': company.id,
                        'organizer_id': org.id,
                        'date_begin': begin,
                        'date_end': begin + timedelta(hours=rnd.choice((2, 3, 4, 8))),
                        'date_tz': 'Europe/Moscow',
                        'seats_max': seats,
                        'seats_limited': True,
                    })
                    past = begin < now
                    for person in rnd.sample(list(people), k=min(len(people), rnd.randint(3, seats - 2))):
                        roll = rnd.random()
                        state = 'cancel' if roll < 0.1 else ('done' if past and roll < 0.8 else 'open')
                        env['event.registration'].sudo().create({
                            'event_id': event.id, 'partner_id': person.id,
                            'name': person.name, 'email': person.email or False,
                            'state': state,
                        })
                    ls._mark(env, xmlid, event)
                    made += 1
            except Exception as exc:  # noqa: BLE001
                _logger.warning('Мероприятия витрины: %s не заведено: %s', xmlid, ls._flat(exc))
    _logger.info('Мероприятия витрины: заведено %s', made)
    return made
