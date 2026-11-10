# -*- coding: utf-8 -*-
"""Контракты проектов и свежие денежные вклады — для аналитики проекта.

№ 395: на странице проекта четыре вкладки аналитики. «Контракты» читает
сделки с `project_id`, «Финансовые вклады» — поступления по неделям. Без
наполнения обе пусты и проверить их не на чем: сделки предмета «Проект»
из каталога ни к одному проекту не привязаны, а даты принятых вкладов
лежат за пределами последних недель.

Идемпотентно: сделок с проектом столько, сколько задано, лишних не
заводится; даты вкладов двигаются один раз (признак — принятие в
последние восемь недель у достаточного числа вкладов).
"""
import logging
import random
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

TARGET_DEALS = 130
RECENT_MONEY = 80
CONTRACT_TITLES = [
    'Монтаж оборудования по проекту', 'Поставка материалов на площадку',
    'Подряд на строительные работы', 'Аренда техники на период сбора',
    'Услуги по проектной документации', 'Логистика и доставка партии',
    'Пусконаладка и обучение персонала', 'Закупка сырья на первую очередь',
    'Юридическое сопровождение проекта', 'Изготовление комплектующих',
]
# Состояния сделок проекта: больше исполняемых, меньше завершённых и
# ждущих приёмки; споры и отмены в аналитике не нужны (отмены не считаются).
STATE_WEIGHTS = ['active'] * 6 + ['done'] * 3 + ['acceptance'] * 2 + ['agreed'] * 1


def _payments(Payment, deal, rnd, today):
    parts = rnd.choice([1, 2, 3, 3, 4])
    remaining = deal.amount
    signed = deal.signed_on or today
    for offset in range(parts):
        last = offset == parts - 1
        value = remaining if last else round(deal.amount / parts)
        remaining -= value
        due = signed + timedelta(days=30 * (offset + 1))
        if deal.state == 'done':
            state = 'paid'
        elif offset == 0 and deal.state in ('active', 'acceptance'):
            state = 'paid'
        else:
            state = 'overdue' if due < today and offset % 2 == 0 else 'planned'
            if due < today and state == 'planned':
                state = 'overdue'
        Payment.create({
            'deal_id': deal.id,
            'name': 'Платёж %s из %s' % (offset + 1, parts) if parts > 1 else 'Оплата по договору',
            'due_on': due, 'amount': value, 'state': state,
            'paid_on': due if state == 'paid' else False,
        })


def load_project_deals(env, target=TARGET_DEALS):
    Deal = env['coop.deal'].sudo().with_context(tracking_disable=True)
    Payment = env['coop.deal.payment'].sudo().with_context(tracking_disable=True)
    Project = env['coop.project'].sudo()
    Partner = env['res.partner'].sudo()
    rnd = random.Random(20261110)
    today = fields.Date.context_today(Deal)

    existing = Deal.search_count([('project_id', '!=', False)])
    projects = Project.search([('state', 'in', ('gathering', 'running', 'done'))],
                              order='id', limit=500)
    orgs = Partner.search([('is_company', '=', True)], order='id', limit=300)
    if not projects or len(orgs) < 2:
        _logger.info('Контракты проектов: нет проектов или организаций, пропуск')
        return 0

    made = 0
    for index, project in enumerate(projects):
        if existing + made >= target:
            break
        if Deal.search_count([('project_id', '=', project.id)]):
            continue
        if index % 3 == 2:
            # Не у каждого проекта есть контракты: часть чисто на вкладах.
            continue
        side_a = project.partner_id
        side_b = orgs[(index * 7) % len(orgs)]
        if side_b == side_a:
            side_b = orgs[(index * 7 + 1) % len(orgs)]
        for step in range(rnd.choice([1, 1, 2, 3])):
            state = rnd.choice(STATE_WEIGHTS)
            signed = today - timedelta(days=rnd.randint(15, 220))
            amount = rnd.choice([48000, 72000, 120000, 185000, 240000, 310000,
                                 450000, 690000, 920000])
            deal = Deal.create({
                'name': '%s «%s»' % (CONTRACT_TITLES[(index + step) % len(CONTRACT_TITLES)],
                                       project.name[:40]),
                'subject': 'project', 'way': 'service',
                'party_a_id': side_a.id, 'party_b_id': side_b.id,
                'role_a': 'исполнитель', 'role_b': 'заказчик',
                'project_id': project.id, 'amount': amount,
                'state': state, 'signed_on': signed,
                'closed_on': signed + timedelta(days=90) if state == 'done' else False,
            })
            Payment.search([('deal_id', '=', deal.id)]).unlink()
            _payments(Payment, deal, rnd, today)
            made += 1
    _logger.info('Контракты проектов: заведено %s', made)
    return made


def spread_recent_money(env, target=RECENT_MONEY):
    """Часть принятых денежных вкладов — в последние восемь недель.

    Столбики поступлений по неделям на пустом хвосте ничего не
    показывают: у живого сбора вклады идут каждую неделю и неровно."""
    Contribution = env['coop.project.contribution'].sudo().with_context(tracking_disable=True)
    today = fields.Date.context_today(Contribution)
    border = today - timedelta(days=56)
    recent = Contribution.search_count([
        ('kind', '=', 'money'), ('state', '=', 'accepted'), ('accepted_on', '>=', border)])
    if recent >= target:
        return 0
    rnd = random.Random(20261111)
    pool = Contribution.search([
        ('kind', '=', 'money'), ('state', '=', 'accepted'),
        ('project_id.state', 'in', ('gathering', 'running')),
        '|', ('accepted_on', '=', False), ('accepted_on', '<', border)], limit=400)
    moved = 0
    for contribution in pool:
        if recent + moved >= target:
            break
        # Больше к концу срока: сбор оживает у финиша.
        days = int(56 * (rnd.random() ** 1.4))
        accepted = today - timedelta(days=days)
        contribution.write({'accepted_on': accepted,
                            'offered_on': accepted - timedelta(days=rnd.randint(0, 3))})
        moved += 1
    _logger.info('Свежие денежные вклады: сдвинуто %s', moved)
    return moved
