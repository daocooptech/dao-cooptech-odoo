# -*- coding: utf-8 -*-
"""Продвижение объявлений: занятые места, история и текущие показы.

Раздел «Продвижение» показывал пустой экран: мест в выдаче двадцать, а
занято не было ни одного. По пустому месту не видно ни цены, ни срока,
ни того, чем платное место отличается от обычной выдачи, — то есть весь
смысл раздела оставался за кадром.

Одно место занято одним объявлением на срок целиком, поэтому периоды у
места не пересекаются: история идёт цепочкой назад от сегодняшнего дня.
Часть мест занята сейчас, часть свободна — свободные места и есть то,
ради чего участник заходит на страницу.
"""
import logging
import random
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

TARGET = 130


def load_promotions(env, target=TARGET):
    Promotion = env['coop.promotion'].sudo()
    Slot = env['coop.promotion.slot'].sudo()
    Resource = env['coop.resource'].sudo()

    slots = Slot.search([], order='page, position')
    resources = Resource.search([('state', '=', 'published')], order='id')
    if not slots or not resources:
        _logger.warning('Нет мест или объявлений — продвижение не наполняю')
        return

    # Повторная загрузка не должна удваивать историю. Сверяться по
    # ключу источника здесь не с чем — записи не из файла, а собраны из
    # мест и сроков, — поэтому признак простой: наполнено ли уже.
    if Promotion.search_count([]) >= target // 2:
        _logger.info('Продвижение: уже наполнено, пропускаю')
        return

    rnd = random.Random(20260907)
    now = fields.Datetime.now()
    created = skipped = 0

    # Витрина участника: часть продвижений — его собственные объявления,
    # иначе он открывает раздел и видит только чужие показы, а своих
    # трат не находит.
    me = env['res.users'].sudo().search([('login', '=', 'dashkevich')], limit=1)
    my_resources = resources.filtered(
        lambda r: me and r.owner_id in me.coop_treasury_partner_ids)

    per_slot = max(2, target // len(slots))
    for slot in slots:
        # Цепочка назад по времени: у одного места периоды не
        # пересекаются, иначе на одной строке выдачи оказались бы два
        # объявления разом.
        # Время суток разное: одинаковые «13:48» во всём столбце выдают
        # машинную генерацию сильнее, чем сами даты.
        cursor = (now + timedelta(days=rnd.randint(-3, 9))).replace(
            hour=rnd.randrange(8, 21), minute=rnd.choice([0, 5, 15, 30, 45]))
        for step in range(per_slot):
            if created >= target:
                break
            days = rnd.choice([3, 7, 7, 14, 14, 30])
            date_to = cursor
            date_from = date_to - timedelta(days=days)

            # Каждое шестое продвижение — своё. Раздел показывает
            # участнику только его собственные траты (чужие закрыты
            # правилом доступа), а объявлений у одного участника
            # несколько — если брать своё чаще, история выглядит как
            # одно и то же объявление, выкупавшее места три десятка раз.
            pool = my_resources if (my_resources and step % 6 == 0) else resources
            resource = pool[rnd.randrange(len(pool))]

            Promotion.create({
                'resource_id': resource.id,
                'slot_id': slot.id,
                'partner_id': resource.owner_id.id,
                'days': days,
                'price_per_day': slot.price_per_day,
                'date_from': date_from,
                'date_to': date_to,
            })
            created += 1
            # Между показами бывает пауза: место не выкупают непрерывно.
            cursor = (date_from - timedelta(days=rnd.choice([0, 0, 1, 3, 8]))).replace(
                hour=rnd.randrange(8, 21), minute=rnd.choice([0, 5, 15, 30, 45]))

    active = Promotion.search_count([('date_from', '<=', now), ('date_to', '>', now)])
    _logger.info('Продвижение: создано %s, пропущено %s, показывается сейчас %s',
                 created, skipped, active)
