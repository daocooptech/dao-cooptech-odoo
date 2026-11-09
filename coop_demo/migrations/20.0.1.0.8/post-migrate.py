# -*- coding: utf-8 -*-
"""Характеристики по веткам дерева каталога ресурсов (задача 399).

Привязки снимаются и ставятся явно, пустые значения добираются; уже
заполненные не затираются. Идемпотентно.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_branch_attributes


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True})
    load_branch_attributes.load_branch_attributes(env)
