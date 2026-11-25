# -*- coding: utf-8 -*-
"""Токены за задачи проектов с токеном (№ 485): оценка и начисления.

Один раз: оценка ставится задачам загрузчиков, у сделанных — начисление
исполнителям датой срока; каждая пятая сделанная ждёт приёмки менеджера.
Наш проект не трогаем — у него только настоящие задачи; проекты и задачи
людей — тоже (созданные не системой).
"""
import logging
import zlib
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

FLAG = 'coop_demo.task_tokens_loaded'


def load_task_tokens(env):
    Config = env['ir.config_parameter'].sudo()
    if 'coop_tokens' not in env['project.task']._fields or Config.get_str(FLAG):
        return 0
    ours = env['coop.bounty.task']._coop_our_project()
    today = fields.Date.context_today(env['project.task'])
    Task = env['project.task'].sudo().with_context(
        tracking_disable=True, mail_create_nolog=True, mail_notrack=True,
        coop_no_emission=True)
    cards = env['coop.project'].sudo().search(
        [('coop_has_token', '=', True), ('project_id', '!=', False)]) - ours
    rated = paid = 0
    for card in cards.filtered(lambda c: c.create_uid.id == 1):
        tasks = Task.search([('project_id', '=', card.project_id.id), ('parent_id', '=', False),
                             ('coop_tokens', '=', 0), ('state', '!=', '1_canceled'),
                             ('create_uid', '=', 1)])
        for task in tasks:
            seed = zlib.crc32(('%s %s' % (card.name, task.name)).encode())
            hours = task.allocated_hours or (4 + seed % 60)
            # Круглой суммой: полсотни токенов, с разбросом по задаче.
            amount = max(100, int(hours * (12 + seed % 9)) // 50 * 50)
            task.coop_tokens = min(amount, 4000)
            rated += 1
        # Выделено с запасом на все задачи: иначе начислять не из чего.
        need = sum(tasks.mapped('coop_tokens')) + card.coop_bounty_blocked + card.coop_bounty_paid
        if card.coop_bounty_token_limit < need:
            card.coop_bounty_token_limit = -(-int(need * 1.25) // 1000) * 1000
        for number, task in enumerate(tasks.filtered(lambda t: t.state == '1_done')):
            if number % 5 == 4 or not task.user_ids:
                continue
            day = task.date_deadline.date() if task.date_deadline else today - timedelta(days=number)
            task.with_context(coop_token_date=min(day, today))._coop_tokens_accrue()
            paid += bool(task.coop_tokens_paid)
    Config.set_str(FLAG, '1')
    _logger.info('Токены за задачи: оценено %s, начислено за %s', rated, paid)
    return paid
