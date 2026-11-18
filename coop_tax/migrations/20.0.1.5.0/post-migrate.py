# -*- coding: utf-8 -*-
"""Акты приёмки по выплатам за задачи (№ 465 п. 20).

У выплат, проведённых до актов, номера нет: присваиваем по порядку дат,
статус исполнителя — по профилю на день переноса (иного источника нет).
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {'mail_notrack': True, 'tracking_disable': True})
    payouts = env['coop.bounty.payout'].search([('act_number', '=', False)], order='date, id')
    payouts._coop_fill_act()
    _logger.info('Акты приёмки: номера присвоены %s выплатам', len(payouts))
