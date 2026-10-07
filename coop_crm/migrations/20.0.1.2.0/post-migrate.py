# -*- coding: utf-8 -*-
"""Приложения организаций по группе правовых форм (решение 450, 08.10.2026).

Набор по умолчанию у всех организаций, затем пересчёт доступа: CRM
теперь даётся только там, где он включён, и группа «все лиды» снимается
у тех, кому её выдавали раньше без полномочия «Сделки».
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orgs = env['res.partner'].with_context(active_test=False).search([('is_company', '=', True)])
    orgs._coop_default_apps()
    group = env.ref('sales_team.group_sale_salesman_all_leads')
    before = env['res.users'].search_count([('share', '=', False), ('group_ids', 'in', group.id)])
    env['res.users']._coop_sync_accounting_access()
    after = env['res.users'].search_count([('share', '=', False), ('group_ids', 'in', group.id)])
    _logger.info('Приложения: набор проставлен у %s организаций; группа «все лиды» '
                 'была у %s, осталась у %s', len(orgs), before, after)
