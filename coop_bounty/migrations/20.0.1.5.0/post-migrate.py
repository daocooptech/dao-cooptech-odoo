# -*- coding: utf-8 -*-
"""Выплаты по задачам (№ 465): у принятых до П2 задач — по одной выплате.

Фонд, «выполненные задачи» и реестр доходов теперь считаются по
выплатам. У задач, принятых раньше, выплата одна — исполнителю на всю
сумму, тем же движением токенов, что уже проведено: новых начислений и
строк реестра перенос не заводит. Дата сдачи — день её создания.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    cr.execute("UPDATE coop_bounty_submission SET date = create_date::date WHERE date IS NULL")
    cr.execute("""UPDATE coop_bounty_task SET paid_amount = reward_tokens
                  WHERE state = 'accepted' AND COALESCE(paid_amount, 0) = 0""")
    cr.execute("UPDATE coop_bounty_task SET dispute_by = 'silence' WHERE state = 'dispute' AND dispute_by IS NULL")
    env = api.Environment(cr, SUPERUSER_ID, {'mail_notrack': True, 'tracking_disable': True})
    Task = env['coop.bounty.task']
    Task.invalidate_model(['paid_amount', 'dispute_by'])
    Payout = env['coop.bounty.payout']
    Move = env['coop.project.token.move']
    tasks = Task.search([('state', '=', 'accepted'), ('reward_tokens', '>', 0),
                         ('assignee_id', '!=', False), ('payout_ids', '=', False)])
    for task in tasks:
        accepted = task.submission_ids.filtered(lambda s: s.state == 'accepted')[:1]
        Payout.create({
            'task_id': task.id,
            'partner_id': task.assignee_id.id,
            'amount': task.reward_tokens,
            'date': task.accepted_on or task.write_date.date(),
            'submission_id': accepted.id,
            'transaction_id': task.reward_transaction_id.id,
            'token_move_id': Move.search([('task_id', '=', task.id)], limit=1).id,
        })
