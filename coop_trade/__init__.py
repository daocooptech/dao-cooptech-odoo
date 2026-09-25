# -*- coding: utf-8 -*-
from . import models


def _post_init(env):
    """Наполнение — сразу при установке, если стоит модуль демо-данных.

    Загрузчик `coop_demo` при обновлении идёт раньше, чем выкатка ставит
    новые модули, и контрактов бы не было до следующего обновления демо.
    """
    if 'coop.demo.loader' in env:
        from odoo.addons.coop_demo.data import load_trade
        load_trade.load_trade(env)
