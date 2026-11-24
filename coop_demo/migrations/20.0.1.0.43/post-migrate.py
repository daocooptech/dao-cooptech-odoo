# -*- coding: utf-8 -*-
"""Свои поля у каждого каталога по Авито и YouDo (№ 483, 24.11.2026):
дерево глубже, наборы характеристик по листам, правдоподобные значения.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_483


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_483.load_483(env)
