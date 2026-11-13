# -*- coding: utf-8 -*-
"""Занятость и график у демо-предложений навыков (решение 661 п. 4,
задача 434)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_skills


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_skills.spread_employment(env)
