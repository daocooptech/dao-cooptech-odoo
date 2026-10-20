# -*- coding: utf-8 -*-
"""Держателям «Бухгалтерии и счетов» — группа «Basic» вместо «Счетов»
(владелец 20.10.2026): панель «Выставления счетов» без неё не открывается."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    group = env.ref('account.group_account_basic')
    before = env['res.users'].search_count([('share', '=', False), ('all_group_ids', 'in', group.id)])
    env['res.users']._coop_sync_accounting_access()
    after = env['res.users'].search_count([('share', '=', False), ('all_group_ids', 'in', group.id)])
    _logger.info('Группа «Basic» бухгалтерии: была у %s, стала у %s', before, after)
