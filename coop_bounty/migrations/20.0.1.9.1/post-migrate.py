# -*- coding: utf-8 -*-
"""«ДАО КООПТЕХ» — в «Моих проектах» владельца (26.11.2026).

Инициатор карточки — рабочая группа, а «Разместил» стоял служебный
OdooBot: ни у кого из людей проект в «Моих проектах» не показывался.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ours = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    owner = env['res.users'].search([('login', '=', 'dashkevich')], limit=1)
    if ours and owner and ours.author_id != owner.partner_id:
        ours.author_id = owner.partner_id
