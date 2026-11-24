# -*- coding: utf-8 -*-
"""Вакансии и навыки: поля по профессии, условия, значения (№ 483)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_483_work


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_483_work.load_483_work(env)
