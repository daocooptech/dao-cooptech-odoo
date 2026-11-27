# -*- coding: utf-8 -*-
"""Табели витрины dashkevich для дашбордов «Расписания» и «Проект» (решение 707)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_showcase_timesheets


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    load_showcase_timesheets.load_showcase_timesheets(env)
