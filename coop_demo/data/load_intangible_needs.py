# -*- coding: utf-8 -*-
"""Потребности проектов в нематериальных активах.

Решение владельца 632 от 28.10.2026: в смете проекта четыре вида, и
нематериальные в ней есть наравне с вещами и трудом. Загрузчик кладёт
эти потребности в проекты — иначе четвёртый список на витрине пуст, и
проверить его не на чем.

Что просят проекты: рецептуры и технологии, программы учёта, товарные
знаки, патенты. Актив берётся у чужого правообладателя — просить у себя
свой же актив незачем.

Разброс намеренный: большинство потребностей открыты, часть закрыта
(кто-то уже внёс), немногие сняты. Оценка — остаточная стоимость актива,
а у актива без стоимости — правдоподобная сумма.
"""
import logging
import random

from odoo import fields

_logger = logging.getLogger(__name__)

TARGET_NEEDS = 130

# Проекты, готовые принимать вклады: черновик и отменённые не в счёт.
OPEN_STATES = ('gathering', 'running')

# Как часто потребность закрыта или снята. Открытых больше: витрина должна
# показывать работу, а не архив.
STATE_WEIGHTS = ['open'] * 12 + ['closed'] * 4 + ['cancelled'] * 1


def load_intangible_needs(env, target=TARGET_NEEDS):
    Need = env['coop.intangible.need'].sudo()
    Project = env['coop.project'].sudo()
    Asset = env['coop.intangible'].sudo()

    rnd = random.Random(20261031)

    assets = Asset.search([('state', 'in', ('active', 'draft'))], limit=600)
    if not assets:
        _logger.info('Потребности в НМА: активов нет, пропуск')
        return

    projects = Project.search([('state', 'in', OPEN_STATES)], limit=600)
    if not projects:
        _logger.info('Потребности в НМА: проектов нет, пропуск')
        return

    made = 0
    closed = 0
    cancelled = 0
    for index, project in enumerate(projects):
        if made >= target:
            break
        # У больших проектов потребностей больше: смета на полтора
        # миллиона редко состоит из одной строки.
        count = 1 if index % 3 else rnd.randint(1, 2)
        for step in range(count):
            asset = assets[(index * 7 + step * 13 + 5) % len(assets)]
            if asset.owner_id == project.partner_id:
                asset = assets[(index * 7 + step * 13 + 61) % len(assets)]
            if asset.owner_id == project.partner_id:
                continue
            if Need.search_count([('project_id', '=', project.id),
                                  ('intangible_id', '=', asset.id)], limit=1):
                continue
            state = rnd.choice(STATE_WEIGHTS)
            price = asset.residual_value or asset.initial_cost or float(
                rnd.randrange(60, 480) * 1000 // 1000 * 1000)
            with env.cr.savepoint():
                Need.create({
                    'project_id': project.id,
                    'intangible_id': asset.id,
                    'price': price,
                    'state': state,
                    'note': 'Нужно для запуска: своё делать дольше, чем '
                            'договориться с правообладателем.',
                    'closed_by_id': project.partner_id.id if state == 'closed' else False,
                    'closed_on': fields.Datetime.now() if state == 'closed' else False,
                })
            made += 1
            closed += 1 if state == 'closed' else 0
            cancelled += 1 if state == 'cancelled' else 0

    _logger.info('Потребности в НМА: создано %d (закрыто %d, снято %d)',
                 made, closed, cancelled)
