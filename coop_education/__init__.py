# -*- coding: utf-8 -*-
from . import models


def _post_init(env):
    """Наполнение сразу при установке, если стоит модуль демо-данных
    (как у `coop_crypto_exchange`: выкатка ставит новые модули раньше, чем
    обновляет загрузчик)."""
    if 'coop.demo.loader' in env:
        from odoo.addons.coop_demo.data import load_courses
        load_courses.load_courses(env)
