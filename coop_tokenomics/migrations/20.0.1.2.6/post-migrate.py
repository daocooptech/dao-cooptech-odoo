# -*- coding: utf-8 -*-
"""Снять доли, начисленные за труд нечлена (решение 659 п. 3, 13.11.2026).

Выпущенные в сеть доли не трогаем: их снятие — отдельная операция в
сети, а не правка записи.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Contribution = env['coop.project.contribution']
    wrong = Contribution.search([
        ('share_excluded', '=', True),
        ('share_tokens', '>', 0),
        ('share_minted', '=', False),
    ])
    if not wrong:
        return
    wrong.write({'share_tokens': 0, 'share_factor_used': 0})
    projects = wrong.project_id
    env.add_to_compute(projects._fields['share_total'], projects)
    env.flush_all()
    rest = projects.contribution_ids
    env.add_to_compute(Contribution._fields['share_percent'], rest)
    env.flush_all()
