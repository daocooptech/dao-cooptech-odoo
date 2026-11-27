# -*- coding: utf-8 -*-
"""Мероприятия витрины dashkevich для дашборда «События» (решение 707)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_showcase_events


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    load_showcase_events.load_showcase_events(env)
