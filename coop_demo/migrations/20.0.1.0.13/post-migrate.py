# -*- coding: utf-8 -*-
"""Основание «Инвестирование» у части коммерческих и ДАО-проектов (задача 387). Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_projects


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    projects = env['coop.project'].search([('import_key', '!=', False)])
    for project in projects:
        load_projects._investment_basis(project, project.import_key)
