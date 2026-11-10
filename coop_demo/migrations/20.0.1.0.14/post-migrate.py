# -*- coding: utf-8 -*-
"""Объявления прибыли проектов и выплаты в демо (задача 387). Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_profits


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_profits.load_profits(env)
