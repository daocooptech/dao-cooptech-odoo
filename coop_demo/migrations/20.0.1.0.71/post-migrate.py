# -*- coding: utf-8 -*-
"""Штатные дашборды организаций с данными (решение 707): у витрины
dashkevich — 150 заказов продаж за год, часть со счетами."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_sales


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    load_sales.load_showcase_sales(env)
