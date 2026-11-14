# -*- coding: utf-8 -*-
"""Сопроводительный текст у заявок на потребности (№ 449, образец
OffersReviewPage): поле `note` появилось у вклада 15.11.2026, демо-заявки
получают текст, четверть остаётся без него.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_project_needs


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_project_needs.fill_offer_notes(env)
