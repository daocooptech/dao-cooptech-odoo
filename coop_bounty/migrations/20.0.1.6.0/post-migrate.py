# -*- coding: utf-8 -*-
"""Резерв задач проекта (решение 689, № 465 кусок 2).

Задача проекта теперь публикуется, только если сумма блокируется из
токенов, которые проект выделил на задачи. У проектов, чьи задачи
опубликованы раньше, выделенного нет — ставим с запасом в четверть от
уже заблокированного и выплаченного, круглым числом: открытые задачи
остаются в силе, а новые проект публикует в пределах своего числа.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {'mail_notrack': True, 'tracking_disable': True})
    projects = env['coop.bounty.task'].search(
        [('payer_kind', '=', 'project'), ('project_id', '!=', False)]).mapped('project_id')
    fitted = projects._coop_bounty_fit_limit()
    _logger.info('Резерв задач проекта: токены на задачи выделены %s проектам', fitted)
