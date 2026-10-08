# -*- coding: utf-8 -*-
"""«Проекты» организаций выключены по умолчанию (решение 452, 08.10.2026).

Выключаются у тех, кто своих проектов в управлении не ведёт; у
организаций-инициаторов остаются включёнными — иначе их проекты пропали
бы из кабинета. Однократно, при переходе на эту версию: повторный проход
затирал бы выбор руководителя.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    internal = env['res.company'].search([]).internal_project_id.ids \
        if 'internal_project_id' in env['res.company']._fields else []
    running = env['project.project'].with_context(active_test=False).search([
        ('id', 'not in', internal), ('partner_id.is_company', '=', True)]).partner_id
    orgs = env['res.partner'].with_context(active_test=False).search([
        ('is_company', '=', True), ('coop_app_project', '=', True)])
    off = orgs - running
    off.write({'coop_app_project': False})
    env['res.users']._coop_sync_accounting_access(off)
    _logger.info('«Проекты» выключены у %s организаций, включены у %s (ведут проекты)',
                 len(off), len(orgs & running))
