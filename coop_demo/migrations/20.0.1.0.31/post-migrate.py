# -*- coding: utf-8 -*-
"""Аукционы освежены от сегодняшнего дня, сделки dashkevich разнесены
по году (решения 654 и 655, 12.11.2026)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import refresh_dates


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    refresh_dates.refresh_auction_dates(env)
    refresh_dates.spread_deal_dates(env)
