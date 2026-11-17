# -*- coding: utf-8 -*-
"""Решение 690: задачи краудсорсинга — только токенами своего проекта.

Задачам платформы — наш проект и токены услуг платформы; задачам
проектов — токены проекта; доля и рубли больше не способ оплаты.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {'mail_notrack': True, 'active_test': False})
    Method = env['coop.bounty.method']
    tokens = Method.search([('code', '=', 'tokens')], limit=1)
    project_tokens = Method.search([('code', '=', 'project_tokens')], limit=1)
    ours = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    for task in env['coop.bounty.task'].search([]):
        method = tokens if task.payer_kind == 'platform' else project_tokens
        values = {'allowed_method_ids': [(6, 0, method.ids)], 'share_percent': 0}
        if task.payment_mode:
            values['payment_mode'] = method.code
        if task.payer_kind == 'platform' and ours and not task.project_id:
            values['project_id'] = ours.id
        # write мимо запрета менять сумму: сумма не меняется.
        task.write(values)
        task.application_ids.write({'method_id': method.id})
