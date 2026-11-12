# -*- coding: utf-8 -*-
"""Пересчёт сохранённых итогов проектов (12.11.2026).

Владелец увидел «собрано 5 215 001 из 6 517 000» при готовности 100 % и
доли вкладов, которые не сходились с оценками: сохранённые `readiness`,
`contribution_total` и `share_percent` отстали от самих вкладов. Число
«нужно» (`required_total`) не трогаем — его можно править руками.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    projects = env['coop.project'].with_context(active_test=False).search([])
    env.add_to_compute(projects._fields['contribution_total'], projects)
    env.add_to_compute(projects._fields['readiness'], projects)
    contributions = env['coop.project.contribution'].search([])
    env.add_to_compute(contributions._fields['share_percent'], contributions)
    env.flush_all()
