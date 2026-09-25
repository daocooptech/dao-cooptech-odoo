# -*- coding: utf-8 -*-
"""История прав для уже заведённых ресурсов и завершённых сделок.

Журнал пишется сам только с этой версии; всё, что случилось раньше,
дописывается один раз, по порядку дат: сначала постановка на учёт, потом
сделки. Постановка ставится не позже первой сделки — у части ресурсов
объявление заведено позже, чем по нему прошла первая продажа.
"""
from datetime import datetime, time, timedelta

from odoo import SUPERUSER_ID, api


def _when(deal):
    day = deal.act_confirmed_on or deal.closed_on or deal.signed_on
    if not day:
        return deal.write_date
    # Время внутри дня — от номера сделки: иначе все сделки дня стояли бы
    # в одну и ту же минуту.
    return datetime.combine(day, time(9)) + timedelta(minutes=(deal.id * 37) % 540)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Transfer = env['coop.resource.transfer']
    deals = env['coop.deal'].search([
        ('state', '=', 'done'), ('resource_id', '!=', False),
        ('way', 'in', ('sale', 'batch', 'gift', 'exchange')),
    ])
    deals = deals.sorted(key=lambda d: (_when(d), d.id))
    first = {}
    for deal in deals:
        first.setdefault(deal.resource_id.id, _when(deal))
    resources = env['coop.resource'].search([
        ('listing_type', '=', 'offer'),
        ('resource_type', 'in', ('material', 'equipment')),
        ('owner_id', '!=', False),
    ])
    for resource in resources:
        date = resource.create_date
        if resource.id in first and first[resource.id] <= date:
            date = first[resource.id] - timedelta(days=2)
        resource._coop_register_rights(date=date)
    for deal in deals:
        deal._coop_record_rights(date=_when(deal))
    env.cr.execute('SELECT count(*) FROM coop_resource_transfer')
    print('coop_deals: история прав — записей %s' % env.cr.fetchone()[0])
