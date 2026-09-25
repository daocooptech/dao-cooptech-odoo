# -*- coding: utf-8 -*-
from . import models


def _post_init(env):
    """Наполнение сразу при установке, если стоит модуль демо-данных
    (как у `coop_trade`: выкатка ставит новые модули после обновления)."""
    if 'coop.demo.loader' in env:
        from odoo.addons.coop_demo.data import load_crypto
        load_crypto.load_crypto(env)
