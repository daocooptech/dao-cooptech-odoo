# -*- coding: utf-8 -*-
"""Обращения из разговоров под dashkevich (задача 412). Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_inquiries


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_inquiries.mark_respond_sources(env)
    load_inquiries.load_inquiries(env)
