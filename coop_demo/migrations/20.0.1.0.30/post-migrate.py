# -*- coding: utf-8 -*-
"""Телефоны людям — кнопка «Показать номер» в объявлениях (12.11.2026). Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_people


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_people.ensure_phones(env)
