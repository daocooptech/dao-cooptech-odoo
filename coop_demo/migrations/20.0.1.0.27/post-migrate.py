# -*- coding: utf-8 -*-
"""Готовность проектов без перебора в десятки раз и названия без второго
срока («Тестировщик, 1 месяц, 1 неделя») — хвост № 406, 12.11.2026.
Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import fit_readiness, tidy_names


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    tidy_names.tidy_all(env)
    fit_readiness.fit_readiness(env)
