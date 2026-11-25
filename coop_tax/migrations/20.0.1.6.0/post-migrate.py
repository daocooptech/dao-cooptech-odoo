# -*- coding: utf-8 -*-
"""Участие членов кооперативов по годам (решение 703)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_tax.hooks import demo_payout_members


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {
        'tracking_disable': True, 'mail_create_nolog': True, 'mail_notrack': True})
    demo_payout_members(env)
