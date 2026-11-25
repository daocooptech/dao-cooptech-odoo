# -*- coding: utf-8 -*-
"""Отклики навыками и услугами на трудовые потребности (№ 474).

Хозяева настоящих предложений каталога откликаются на потребности той же
специализации: ставка — их, количество подобрано к стоимости строки. В
наборе есть отклонённые, ждущие ответа и с встречной ставкой. Повторный
запуск ничего не добавляет.
"""
import logging
import random
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)
TARGET = 160
WORDS = (
    'Готов начать в течение недели.', 'Инструмент свой.',
    'Работал на похожем объекте, покажу фотографии.',
    'Могу совмещать, полдня в будни.', 'Нужен подъезд и временное питание.',
    'Беру целиком, с отчётом по этапам.', 'Приеду с напарником.', '',
)


def load_474_skills(env):
    Contribution = env['coop.project.contribution']
    if Contribution.search_count([('skill_offer_id', '!=', False)], limit=1):
        return
    rnd = random.Random(474)
    needs = env['coop.resource'].search([
        ('project_id.state', 'in', ('gathering', 'running')),
        ('resource_type', '=', 'labour'), ('state', '=', 'published'),
        ('need_specialization_id', '!=', False)], order='id')
    owner = env['res.users'].search([('login', '=', 'dashkevich')], limit=1)
    mine = owner.coop_actor_partner_ids if owner else env['res.partner']
    # Проекты владельца — первыми: набор должен быть виден у него.
    order = {need.id: rnd.random() for need in needs}
    needs = needs.sorted(lambda n: (n.project_id.partner_id not in mine, order[n.id]))
    offers = env['coop.skill.offer'].search([
        ('state', '=', 'published'), ('rate', '>', 0),
        ('rate_kind', '!=', 'piece')], order='id')
    by_spec = {}
    for offer in offers:
        by_spec.setdefault(offer.coop_specialization_id.id, []).append(offer)
    today = fields.Date.today()
    made = 0
    for need in needs:
        if made >= TARGET:
            break
        project = need.project_id
        taken = need.need_offer_ids.partner_id | project.partner_id
        pool = [o for o in by_spec.get(need.need_specialization_id.id, [])
                if o.partner_id not in taken
                and (not project._coop_members_only()
                     or project._coop_is_member(o.partner_id))]
        rnd.shuffle(pool)
        for offer in pool[:rnd.choice((1, 1, 2, 3))]:
            rate = offer.rate
            if offer.currency_id != project.currency_id:
                rate = offer.currency_id._convert(
                    rate, project.currency_id, env.company, today)
            if not rate:
                continue
            cap = {'month': 6, 'day': 30, 'hour': 160}.get(offer.rate_period, 2)
            qty = min(cap, max(1, round((need.price or rate) / rate)))
            state = rnd.choices(('offered', 'declined'), (85, 15))[0]
            Contribution.create({
                'project_id': project.id, 'need_id': need.id,
                'partner_id': offer.partner_id.id, 'kind': 'labour',
                'name': offer.name, 'skill_offer_id': offer.id,
                'labour_rate': rate, 'labour_period': offer.rate_period or 'job',
                'labour_qty': qty, 'value': rate * qty, 'state': state,
                'counter_rate': (round(rate * rnd.choice((0.8, 0.85, 0.9)), -1)
                                 if state == 'offered' and rnd.random() < 0.15 else 0),
                'note': rnd.choice(WORDS),
                'offered_on': today - timedelta(days=rnd.randint(0, 45)),
            })
            made += 1
        rest = [o for o in pool[3:] if rnd.random() < 0.3][:3]
        if rest:
            need.need_invited_offer_ids = [(4, o.id) for o in rest]
    _logger.info('N 474: откликов навыками %s', made)
