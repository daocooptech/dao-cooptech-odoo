# -*- coding: utf-8 -*-
"""Готовность проектов без перебора в десятки раз (хвост задачи 406, 12.11.2026).

Готовность считается без потолка намеренно (`_compute_readiness`): перебор
должен быть виден. Но в демо он вышел не перебором, а сбоем: у
«Фельдшерского пункта» 43 429 %, у «Круглогодичной теплицы» 2 582 %.

Причин две. У части потребностей проекта цена-заглушка 1 ₽ — «Нужно»
складывалось из единиц. И крупные вклады в демо не привязаны к
потребностям (помещение на 1,7 млн при «Нужно» в 12 тысяч), а в
«Собрано» идут все принятые.

Чиним данные, не расчёт: заглушке — медианная цена такой же потребности
в других проектах; где перебор всё ещё больше 120 %, непривязанные
принятые вклады уменьшаются пропорционально до правдоподобной доли
«Нужно» — у собирающих 55–95 %, у работающих и завершённых 100–115 %.
Привязанные к потребности вклады не трогаем: их сумма — это сумма
закрытой строки. Повторный запуск ничего не меняет.
"""
import collections
import logging

_logger = logging.getLogger(__name__)

LIMIT = 120          # перебор выше этого — сбой наполнения
GATHERING = (55, 95)  # доля «Нужно», %, у собирающих
FUNDED = (100, 115)   # у работающих и завершённых


def _base(name):
    return (name or '').split(',')[0].split(' — ')[0].strip().lower()


def fix_need_prices(env):
    Resource = env['coop.resource'].sudo().with_context(
        active_test=False, tracking_disable=True, mail_notrack=True)
    needs = Resource.search([('project_id', '!=', False), ('listing_type', '=', 'request')])
    priced = collections.defaultdict(list)
    by_type = collections.defaultdict(list)
    for need in needs:
        if (need.price or 0) > 1:
            priced[_base(need.name)].append(need.price)
            by_type[need.resource_type].append(need.price)
    def median(values):
        values = sorted(values)
        return values[len(values) // 2] if values else 0
    fixed = 0
    for need in needs.filtered(lambda r: (r.price or 0) <= 1):
        price = median(priced.get(_base(need.name), [])) or median(by_type.get(need.resource_type, []))
        if price:
            need.price = price
            fixed += 1
    return fixed


def _target(project):
    low, high = GATHERING if project.state in ('draft', 'gathering') else FUNDED
    return (low + (project.id * 7) % (high - low + 1)) / 100.0


def fit_overfunded(env):
    Project = env['coop.project'].sudo().with_context(
        active_test=False, tracking_disable=True, mail_notrack=True)
    projects = Project.search([('readiness', '>', LIMIT)])
    fitted = 0
    for project in projects:
        accepted = project.contribution_ids.filtered(lambda c: c.state == 'accepted')
        loose = accepted.filtered(lambda c: not c.need_id and c.value > 0)
        tied = sum((accepted - loose).mapped('value'))
        # Привязанные уже закрыли почти всю долю — непривязанным остаётся
        # немного, а не ноль: вклад был, просто небольшой.
        goal = max(project.required_total * _target(project) - tied,
                   project.required_total * 0.05)
        current = sum(loose.mapped('value'))
        if not loose or goal <= 0 or current <= goal:
            continue
        factor = goal / current
        for contribution in loose:
            # Круглые суммы, как вносят люди: до сотни рублей.
            contribution.value = max(100.0, round(contribution.value * factor, -2))
        fitted += 1
    return fitted


def fit_readiness(env):
    prices = fix_need_prices(env)
    # «Нужно» и готовность — хранимые и зависят от цены потребности:
    # пересчитываются сами, до отбора по готовности их надо сбросить в базу.
    env.flush_all()
    fitted = fit_overfunded(env) if 'coop.project' in env else 0
    _logger.info('Готовность проектов: цена у %s потребностей, вклады подогнаны у %s проектов',
                 prices, fitted)
    return prices, fitted
