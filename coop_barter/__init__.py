# -*- coding: utf-8 -*-
from . import models


def _post_init(env):
    """Наполнение сразу при установке — как у `coop_mining`."""
    if 'coop.demo.loader' in env:
        from odoo.addons.coop_demo.data import load_barter
        load_barter.load_barter(env)
