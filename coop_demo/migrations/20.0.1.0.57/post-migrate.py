# -*- coding: utf-8 -*-
"""Вид токена у демо-проектов (решение 702, № 485)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_bounty


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {
        'tracking_disable': True, 'mail_create_nolog': True, 'mail_notrack': True})
    load_bounty.fill_token_kinds(env)
