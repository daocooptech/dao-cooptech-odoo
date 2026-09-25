# -*- coding: utf-8 -*-
from . import models


def _post_init(env):
    """Наполнение сразу при установке — как у `coop_trade`."""
    if 'coop.demo.loader' in env:
        from odoo.addons.coop_demo.data import load_mining
        load_mining.load_mining(env)
