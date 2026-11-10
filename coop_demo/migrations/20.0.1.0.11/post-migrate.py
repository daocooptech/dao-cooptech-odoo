# -*- coding: utf-8 -*-
"""Опт и розница: ступени и единицы в демо (задача 401). Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_wholesale


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_wholesale.load_wholesale(env)
