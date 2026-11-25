# -*- coding: utf-8 -*-
"""Описание демо-проекта убрано (владелец 26.11.2026)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Project = env['coop.project']
    Project.search([('description', 'ilike', 'RetroPGF')]).write({'description': False})
    Project.search([('summary', 'ilike', 'RetroPGF')]).write({'summary': False})
