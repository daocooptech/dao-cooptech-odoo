# -*- coding: utf-8 -*-
"""Цены демо-объявлений — как в жизни: в основном точная сумма.

Владелец 27.10.2026: «надо цены нормально проставить, что значит от,
такое бывает но редко, в основном точная сумма же». В наборе почти все
объявления стояли «от» — так было по умолчанию. Раз и навсегда: дальше
уточнение цены — дело владельца объявления, повторный прогон его не
трогает.

Распределение — по номеру записи, чтобы пересборка базы давала то же:
около 85 % «ровно», около 8 % «от», около 4 % «до»; у обмена и
безвозмездной передачи без оценки — «по договорённости».
"""
from odoo import SUPERUSER_ID, api


def _kind(term_id, code, price):
    if code in ('barter', 'free') and not price:
        return 'none'
    if term_id % 12 == 0:
        return 'from'
    if term_id % 25 == 7:
        return 'to'
    return 'exact'


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True})
    Resource = env['coop.resource'].with_context(active_test=False)
    for term in env['coop.resource.term'].search([]):
        term.price_kind = _kind(term.id, term.code, term.price)
    for resource in Resource.search([('term_ids', '=', False)]):
        resource.price_kind = _kind(resource.id, False, resource.price) \
            if resource.price else 'none'
    Resource.search([('term_ids', '!=', False)])._coop_price_from_terms()
