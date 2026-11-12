# -*- coding: utf-8 -*-
"""Заказы продаж и закупок организаций вместо латинского образца Odoo
(решение 655, задача 431) и общие заметки организаций (задача 428)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_org_notes, load_sales


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_sales.load_sales(env)
    load_sales.load_purchases(env)
    load_org_notes.load_org_notes(env)
