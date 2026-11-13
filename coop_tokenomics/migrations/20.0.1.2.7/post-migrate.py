# -*- coding: utf-8 -*-
"""Решение 676 (13.11.2026): вернуть доли, снятые по 659 п. 3.

Вкладчики-нечлены приняты в члены миграцией `coop_projects`, и их
принятые вклады снова дают долю — по ставке проекта, как при принятии.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Contribution = env['coop.project.contribution']
    zero = Contribution.search([
        ('state', '=', 'accepted'), ('share_tokens', '=', 0),
        ('share_factor_used', '=', 0), ('value', '>', 0),
    ])
    for contribution in zero:
        contribution._grant_shares()
    env.flush_all()
    projects = zero.project_id
    env.add_to_compute(projects._fields['share_total'], projects)
    env.flush_all()
    rest = projects.contribution_ids
    env.add_to_compute(Contribution._fields['share_percent'], rest)
    env.flush_all()
