# -*- coding: utf-8 -*-
"""Пулы проектов вместо фарминга (решения 434–436, 28.09.2026): доля
выручки с потолком, выплаты с подтверждением, рублёвые пулы через ЦФА
(учебный выпуск), комиссия DEX с возвратом по обороту. Наполнение —
загрузчик версии 2: пулы загрузчика пересобираются, стакан и история
обменов не трогаются. Однократно — отметка версии в параметрах."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    cr.execute("SELECT 1 FROM ir_module_module WHERE name = 'coop_demo' AND state = 'installed'")
    if not cr.fetchone():
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.coop_demo.data import load_farm
    load_farm.load_dex_farm(env)
