# -*- coding: utf-8 -*-
"""Архив выданных УПД до перехода на РСБУ-слой (задача 294, К1).

См. `models/upd_legacy.py`. Повторный запуск безопасен: счета с архивом
пропускаются.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['account.move']._coop_archive_upd_xml()
