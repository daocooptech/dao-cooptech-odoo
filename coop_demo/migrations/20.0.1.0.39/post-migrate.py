# -*- coding: utf-8 -*-
"""Заявки на потребности — с объявлением по теме (владелец 14.11.2026).

На «Игровой комплекс» приходило «место под мастерскую», а у трети заявок
ресурса не было вовсе: карточка ресурса в разборе заявок показывала чужое
или ничего. Перепривязываем все вещественные заявки к объявлениям той же
основы, недостающие заводим — сразу, а не со следующей загрузкой демо.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_project_needs


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_project_needs.link_offers_to_resources(env)
    load_project_needs.set_ownership_kinds(env)
