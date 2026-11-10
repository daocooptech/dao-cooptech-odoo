# -*- coding: utf-8 -*-
"""«Участие в проекте» — проекты, направления, где (№ 397). Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_resource_terms


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_resource_terms.fill_project_terms(env)
