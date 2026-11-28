# -*- coding: utf-8 -*-
"""Лиды витрины dashkevich для дашборда «Аналитика → CRM» (задача 494)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_showcase_crm


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    load_showcase_crm.load_showcase_crm(env)
