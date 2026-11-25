# -*- coding: utf-8 -*-
"""Допэмиссия под задачи нашего проекта, оценённые без резерва в фонде (№ 485).

Оценка поставлена до правила «допэмиссия — в момент создания задачи», и
задачи краудсорсинга с резервом у них нет: № 474, 477, 485.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ours = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    if not ours or not ours.project_id:
        return
    tasks = env['project.task'].search([
        ('project_id', '=', ours.project_id.id), ('coop_tokens', '>', 0),
        ('coop_tokens_paid', '=', 0), ('coop_tokens_emitted', '=', 0),
        ('state', 'not in', ('1_done', '1_canceled'))])
    tasks = tasks.filtered(lambda t: not t._coop_token_crowd())
    tasks._coop_tokens_emit({})
    _logger.info('Допэмиссия под задачи: %s', tasks.mapped('name'))
