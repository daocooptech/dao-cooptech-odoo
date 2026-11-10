# -*- coding: utf-8 -*-
"""ЦФА под проекты (№ 395): привязка выпусков к проектам эмитента. Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_project_deals


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_project_deals.link_cfa_to_projects(env)
    load_project_deals.place_project_cfa(env)
