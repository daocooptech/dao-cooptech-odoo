# -*- coding: utf-8 -*-
"""Фарминг и глубокий стакан DEX (владелец 26.09.2026): наполнить сразу при
обновлении, если стоит модуль демо-данных. Загрузчик однократный — отметка
версии в параметрах; повторный прогон ничего не добавит."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    cr.execute("SELECT 1 FROM ir_module_module WHERE name = 'coop_demo' AND state = 'installed'")
    if not cr.fetchone():
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.coop_demo.data import load_farm
    load_farm.load_dex_farm(env)
