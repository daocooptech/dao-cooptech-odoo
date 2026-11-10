# -*- coding: utf-8 -*-
"""Аналитика проекта (№ 395): контракты проектов и свежие денежные вклады. Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_project_deals


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    if 'coop.deal' in env:
        load_project_deals.load_project_deals(env)
    load_project_deals.spread_recent_money(env)
    load_project_deals.link_cfa_to_projects(env)
