# -*- coding: utf-8 -*-
"""Решение 676 (13.11.2026): вклад в кооперативный проект — только член.

Демо по выбору владельца: вкладчиков-нечленов оформить членами
кооператива с датой вступления до первого вклада; вклады и паи
остаются. Колонка `share_excluded` (659 п. 3) больше не нужна.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['coop.project']._coop_admit_contributors()
    env.flush_all()
    cr.execute('ALTER TABLE coop_project_contribution '
               'DROP COLUMN IF EXISTS share_excluded')
    contributions = env['coop.project.contribution'].search([])
    env.add_to_compute(contributions._fields['share_percent'], contributions)
    env.flush_all()
    # Решение 665 п. 3: пожертвование — только у тех, кто вправе его
    # принять; у коммерческих организаций и проектов — «Поддержка».
    from odoo.addons.coop_projects.models.coop_project import NO_DONATION_FORMS
    projects = env['coop.project'].with_context(active_test=False).search([
        ('contribution_basis', '=', 'donation'),
        '|', ('kind', '=', 'commercial'),
        '&', ('partner_id.is_company', '=', True),
        ('partner_id.coop_legal_form_id.code', 'in', list(NO_DONATION_FORMS)),
    ])
    projects.write({'contribution_basis': 'prepay'})
    env.flush_all()
