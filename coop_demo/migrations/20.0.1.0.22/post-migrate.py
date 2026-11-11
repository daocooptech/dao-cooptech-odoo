# -*- coding: utf-8 -*-
"""Обращения по предложениям навыков под dashkevich (11.11.2026). Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_inquiries


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_inquiries.load_skill_inquiries(env)
