# -*- coding: utf-8 -*-
"""Названия без городов и рубрики по смыслу (№ 406, 12.11.2026): город и
проект уходят из названий, копии различаются содержанием, «Молоковоз» и
прочие — в свои рубрики, тип объявления — из рубрики. Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import tidy_names


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    tidy_names.tidy_all(env)
