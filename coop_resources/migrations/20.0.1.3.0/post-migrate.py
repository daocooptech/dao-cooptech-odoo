# -*- coding: utf-8 -*-
"""Цена объявления — во вкладку способа (владелец 27.10.2026).

Условия теперь вносятся во вкладках способов, и цена на карточке берётся
из первой вкладки, где она указана. У заведённых раньше объявлений цена
стоит на самом объявлении, а строки условий пустые — вкладка открылась
бы без цены. Переносим её в первый денежный способ, если ни в одном
способе цены ещё нет.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True})
    resources = env['coop.resource'].with_context(active_test=False).search(
        [('method_ids', '!=', False), ('price', '>', 0)])
    resources._coop_sync_terms()
    for resource in resources:
        terms = resource.term_ids.sorted('sequence')
        if any(terms.mapped('price')):
            continue
        first = terms.filtered('method_id.is_monetary')[:1]
        if first:
            first.write({'price': resource.price,
                         'price_unit_label': resource.price_unit_label or False})
