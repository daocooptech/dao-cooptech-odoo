# -*- coding: utf-8 -*-
"""Ремонт: «Черновая отделка» и ещё объявления (задача 399, 10.11.2026). Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_branch_attributes, load_empty_leaves


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_empty_leaves.load_empty_leaves(env)
    load_branch_attributes.load_branch_attributes(env)
