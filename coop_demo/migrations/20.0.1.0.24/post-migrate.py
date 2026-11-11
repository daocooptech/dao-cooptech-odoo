# -*- coding: utf-8 -*-
"""Обращения по навыкам по-настоящему (№ 418, 11.11.2026): у навыка
dashkevich — несколько входящих вместо 38, недостающие — по другим
навыкам, суммы разные. Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_inquiries


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_inquiries.trim_skill_inquiries(env)
    load_inquiries.load_skill_inquiries(env)
    load_inquiries.vary_skill_amounts(env)
