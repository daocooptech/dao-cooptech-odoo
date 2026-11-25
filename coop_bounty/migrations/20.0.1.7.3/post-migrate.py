# -*- coding: utf-8 -*-
"""COOP — утилитарный токен (решение 702)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ours = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    if ours and not ours.coop_token_kind:
        ours.coop_token_kind = 'utility'
