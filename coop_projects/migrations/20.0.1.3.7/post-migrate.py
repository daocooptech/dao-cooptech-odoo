# -*- coding: utf-8 -*-
"""Труд нечлена — без пая (решение 659 п. 3, 13.11.2026).

Новое поле `share_excluded` считается при установке колонки, а пай
остальных вкладов того же проекта надо пересчитать: делитель теперь без
труда нечленов.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Contribution = env['coop.project.contribution']
    contributions = Contribution.search([])
    env.add_to_compute(Contribution._fields['share_excluded'], contributions)
    env.flush_all()
    env.add_to_compute(Contribution._fields['share_percent'], contributions)
    env.flush_all()
