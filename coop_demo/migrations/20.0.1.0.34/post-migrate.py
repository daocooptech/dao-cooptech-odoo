# -*- coding: utf-8 -*-
"""Чистка копий, которые плодила каждая выкатка (задача 443)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import dedupe_443


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    dedupe_443.dedupe_all(env)
