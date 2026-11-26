# -*- coding: utf-8 -*-
"""№ 438: у выпусков и заявок биржи токенов — раздел их ресурса.

Сохранённый «Раздел» (`resource_id.category_id`) у 24 выпусков отстал от
ресурса: у ресурса раздел есть, у выпуска пусто, и 51 заявка биржи висела
вне полок. Пересчёт идёт от ресурса и на правильных записях ничего не меняет.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Claim = env['coop.token.claim'].with_context(active_test=False)
    claims = Claim.search([])
    env.add_to_compute(Claim._fields['resource_category_id'], claims)
    env.flush_all()
    Order = env['coop.token.order'].with_context(active_test=False)
    orders = Order.search([])
    env.add_to_compute(Order._fields['resource_category_id'], orders)
    env.flush_all()
