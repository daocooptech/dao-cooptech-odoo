# -*- coding: utf-8 -*-
"""Склад витрины dashkevich для дашборда «Показатели склада» (решение 707)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_showcase_stock


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    load_showcase_stock.load_showcase_stock(env)
