# -*- coding: utf-8 -*-
"""Строки условий по способам передачи (решение 412, Н5) — у всех
объявлений, где способы уже отмечены. Заполняет их наполнение
(`coop_demo`) или владелец."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    resources = env['coop.resource'].with_context(active_test=False).search(
        [('method_ids', '!=', False)])
    resources._coop_sync_terms()
