# -*- coding: utf-8 -*-
"""Объявления в заявках — с названиями как в жизни (владелец 14.11.2026).

«Игровой комплекс, от организации, с договором, после одного проекта» —
не объявление, а набор хвостов; к части ещё дописывала уточнения чистка
одинаковых названий. Переименовываем в «Игровой комплекс KSIL «Крепость»
7×5 м, б/у 2 сезона» — модель, размер, состояние; названия не совпадают.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_project_needs


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_project_needs.link_offers_to_resources(env)
