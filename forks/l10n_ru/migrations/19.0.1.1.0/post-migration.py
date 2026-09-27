# -*- coding: utf-8 -*-
"""Правка плана счетов 28.09.2026 — довести созданные компании до шаблона.

Шаблон читается из CSV только при загрузке; обновление модуля его к
компании заново не применяет. См. `_coop_ru_refresh` в models/template_ru.py.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['account.chart.template']._coop_ru_refresh()
