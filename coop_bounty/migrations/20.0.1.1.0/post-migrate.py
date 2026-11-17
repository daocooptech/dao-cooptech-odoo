# -*- coding: utf-8 -*-
"""Задачи, заведённые до способов оплаты и фонда (решения 671–673).

У всех прежних задач автор — платформа, и способ был один на задачу.
Теперь автор отмечает допустимые способы, исполнитель выбирает свой:
прежним задачам платформы допустимы оба её способа, у неразобранных
(черновик, опубликовано) выбранного способа ещё нет. Открытые и
принятые задачи платформы относятся к первому фонду — иначе его
резерв не видел бы задач, опубликованных до него.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {'mail_notrack': True})
    methods = env['coop.bounty.method'].search([('scope', '=', 'platform')])
    fund = env.ref('coop_bounty.fund_2026_11', raise_if_not_found=False)
    for task in env['coop.bounty.task'].search([]):
        values = {}
        if task.payer_kind == 'platform' and not task.allowed_method_ids:
            values['allowed_method_ids'] = [(6, 0, methods.ids)]
        if task.state in ('draft', 'published') and task.payment_mode:
            values['payment_mode'] = False
        if (task.payer_kind == 'platform' and fund and not task.fund_id
                and task.state not in ('draft', 'cancelled')):
            values['fund_id'] = fund.id
        if task.state == 'submitted' and not task.submitted_on:
            values['submitted_on'] = task.write_date.date()
        if values:
            task.write(values)
