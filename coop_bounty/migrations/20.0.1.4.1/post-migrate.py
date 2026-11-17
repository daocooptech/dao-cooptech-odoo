# -*- coding: utf-8 -*-
"""Наш проект в краудсорсинге — запущенный (№ 466).

Проект «ДАО КООПТЕХ» был заведён «Идеей»: идею видит только инициатор,
и карточка «Помощь проекту» отвечала участникам «Ошибка доступа».
Платформа работает — проект запущен; порог 100 %, сбора у него нет.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {'mail_notrack': True})
    ours = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    if ours and ours.state == 'draft':
        ours.write({'funding_threshold': 100, 'state': 'running'})
