# -*- coding: utf-8 -*-
"""«Кто делает и из чего» — выдуманное снято (№ 484, 24.11.2026)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_484


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_484.load_484(env)
