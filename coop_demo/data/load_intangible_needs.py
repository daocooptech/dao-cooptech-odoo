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
(кто-то уже внёс), немногие сняты.

11.11.2026. Загрузчик вызывается при каждом обновлении модуля
(`coop_load.xml`) и раньше каждый раз добавлял ещё ~130 строк: к ноябрю
у проекта набиралось до 62 потребностей, и нематериальные в сумме были
больше всего проекта. Теперь проект, у которого строки уже есть, не
трогается, строк — от одной до трёх, а оценка — доля от сметы проекта
(решение 652: «Нужно» — сумма всех четырёх списков, пай строки — её
доля в нём), а не остаточная стоимость актива: товарный знак за
полмиллиона в проекте на триста тысяч неправдоподобен.
"""
import logging
import random

from odoo import fields

_logger = logging.getLogger(__name__)

# Проекты, готовые принимать вклады: черновик и отменённые не в счёт.
OPEN_STATES = ('gathering', 'running')

# Как часто потребность закрыта или снята. Открытых больше: витрина должна
# показывать работу, а не архив.
STATE_WEIGHTS = ['open'] * 12 + ['closed'] * 4 + ['cancelled'] * 1

# Сколько строк на проект: чаще одна-две, у части — три.
COUNT_WEIGHTS = [1] * 4 + [2] * 4 + [3] * 2

NOTE = ('Нужно для запуска: своё делать дольше, чем договориться с '
        'правообладателем.')


def nice_price(base, rnd):
    """Оценка НМА — 4–12 % от сметы остальных трёх списков, круглая.

    Права в смете — заметная, но не главная часть: рецептура или программа
    учёта стоит меньше цеха и людей, которые по ней работают.
    """
    raw = max(base, 300000) * rnd.uniform(0.04, 0.12)
    step = 1000 if raw < 50000 else 5000 if raw < 300000 else 10000
    return float(max(step, round(raw / step) * step))


def resources_total(project):
    return sum(project.need_ids.filtered(
        lambda n: n.state in ('published', 'closed')).mapped('price'))


def load_intangible_needs(env):
    Need = env['coop.intangible.need'].sudo()
    Project = env['coop.project'].sudo()
    Asset = env['coop.intangible'].sudo()

    rnd = random.Random(20261031)

    assets = Asset.search([('state', 'in', ('active', 'draft'))], limit=600)
    if not assets:
        _logger.info('Потребности в НМА: активов нет, пропуск')
        return

    projects = Project.search([('state', 'in', OPEN_STATES)], limit=600)
    have = set(Need.search([('project_id', 'in', projects.ids)]).mapped('project_id').ids)

    made = closed = cancelled = 0
    for index, project in enumerate(projects):
        if project.id in have:
            continue
        base = resources_total(project)
        used = set()
        for step in range(rnd.choice(COUNT_WEIGHTS)):
            asset = assets[(index * 7 + step * 13 + 5) % len(assets)]
            if asset.owner_id == project.partner_id:
                asset = assets[(index * 7 + step * 13 + 61) % len(assets)]
            # Один и тот же актив дважды и одноимённые активы разных
            # правообладателей в одном проекте — повтор, а не смета.
            if asset.owner_id == project.partner_id or asset.name in used:
                continue
            used.add(asset.name)
            state = rnd.choice(STATE_WEIGHTS)
            with env.cr.savepoint():
                Need.create({
                    'project_id': project.id,
                    'intangible_id': asset.id,
                    'price': nice_price(base, rnd),
                    'state': state,
                    'note': NOTE,
                    'closed_by_id': project.partner_id.id if state == 'closed' else False,
                    'closed_on': fields.Datetime.now() if state == 'closed' else False,
                })
            made += 1
            closed += state == 'closed'
            cancelled += state == 'cancelled'

    _logger.info('Потребности в НМА: создано %d (закрыто %d, снято %d)',
                 made, closed, cancelled)


def shrink_intangible_needs(env):
    """Убрать накопленные повторы (11.11.2026). Идемпотентно.

    У проекта остаются строки, на которые уже есть вклад, и до трёх
    первых открытых или закрытых — с разными названиями актива. Оценка
    оставшихся без вклада — доля от сметы проекта (`nice_price`). Снятые
    строки удаляются, если их больше одной на проект.
    """
    Need = env['coop.intangible.need'].sudo()
    Contribution = env['coop.project.contribution'].sudo()
    rnd = random.Random(20261111)

    linked = set(Contribution.search(
        [('need_intangible_id', '!=', False)]).mapped('need_intangible_id').ids)
    drop = Need.browse()
    reprice = []
    for project in Need.search([]).mapped('project_id'):
        rows = Need.search([('project_id', '=', project.id)], order='id')
        names, kept, cancelled_kept = set(), 0, False
        base = resources_total(project)
        for need in rows:
            name = need.intangible_id.name
            if need.id in linked:
                names.add(name)
                continue
            if need.state == 'cancelled':
                if cancelled_kept or name in names:
                    drop |= need
                else:
                    cancelled_kept = True
                    names.add(name)
                continue
            if kept >= 3 or name in names:
                drop |= need
                continue
            kept += 1
            names.add(name)
            reprice.append((need, nice_price(base, rnd)))
    removed = len(drop)
    drop.unlink()
    for need, price in reprice:
        if need.price != price:
            need.price = price
    _logger.info('Потребности в НМА: удалено повторов %d, переоценено %d',
                 removed, len(reprice))
