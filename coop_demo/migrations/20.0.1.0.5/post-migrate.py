# -*- coding: utf-8 -*-
"""Поля способов передачи у демо-объявлений (решение 629).

Владелец 27.10.2026: во вкладках «Продажа», «Аренда», «Лизинг» и других —
свои данные: партия и гарантия, оператор и «свободно с», срок и первый
взнос, выкуп и лизингодатель, доля в проекте, доплата при обмене. Строки
условий уже есть; заполняются только пустые поля.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_resource_terms


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True})
    load_resource_terms.fill_term_details(env)
