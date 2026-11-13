# -*- coding: utf-8 -*-
"""Решение 659 п. 2: делитель распределения у внесённых лет демо."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_tax.hooks import demo_payout_divisor


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True})
    demo_payout_divisor(env)
