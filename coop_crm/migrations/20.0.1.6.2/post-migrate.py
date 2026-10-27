# -*- coding: utf-8 -*-
"""Склады учёта у организаций со «Складом» или «Производством».

До 20.0.1.6.2 склад не заводился вовсе (движок 20 делает это только в
тестах), и приложение «Склад» у включивших его организаций стояло пустым.
Каждому складу организации на платформе — свой склад в учёте.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True})
    orgs = env['res.partner'].search([
        ('is_company', '=', True), ('coop_company_id', '!=', False),
        '|', ('coop_app_stock', '=', True), ('coop_app_mrp', '=', True)])
    orgs._coop_ensure_warehouse()
