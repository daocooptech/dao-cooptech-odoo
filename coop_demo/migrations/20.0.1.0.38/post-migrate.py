# -*- coding: utf-8 -*-
"""Ресурсы без копий (задача 433).

Загрузчики отработали раньше миграции — при старых копиях почти ничего не
завели. После чистки люди, у которых остались только копии, получают
свои, разные объявления сразу, а не со следующей выкаткой.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import dedupe_433, load_spread


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    dedupe_433.dedupe_resources(env)
    load_spread.ensure_personal_needs(env)
    load_spread.ensure_personal_offers(env)
