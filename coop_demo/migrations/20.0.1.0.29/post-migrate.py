# -*- coding: utf-8 -*-
"""Demo notes on To-Do (task 426). Idempotent."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_project_notes


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_project_notes.load_project_notes(env)
