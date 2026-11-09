# -*- coding: utf-8 -*-
"""Земля, гаражи и пустые листья дерева каталога (задачи 398 и 399).

Загрузчик демо на боевой не запускается, поэтому объявления в новых
рубриках заводит миграция. Обе функции идемпотентны: запись узнаётся по
названию, городу и рубрике.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_empty_leaves, load_land_garage


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True})
    load_land_garage.load_land_garage(env)
    load_empty_leaves.load_empty_leaves(env)
