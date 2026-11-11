# -*- coding: utf-8 -*-
"""Доверие участников с тонкой историей отзывов (11.11.2026). Идемпотентно.

ПК «Молочный путь»: две сделки, один отзыв-тройка — доверие 0 %.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_examples


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_examples.balance_thin_trust(env)
