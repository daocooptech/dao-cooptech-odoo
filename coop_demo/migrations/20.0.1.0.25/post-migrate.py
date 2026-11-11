# -*- coding: utf-8 -*-
"""Знаки организаций вместо заглушки движка «Your logo» (№ 419,
11.11.2026): у организаций с компанией учёта знак затирался при её
создании. Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_orgs


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_orgs.repair_default_logos(env)
