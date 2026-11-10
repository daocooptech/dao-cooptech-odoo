# -*- coding: utf-8 -*-
"""Валюты, счета и операции кошелька в демо (задача 400). Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_wallet_currencies


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_wallet_currencies.load_wallet_currencies(env)
