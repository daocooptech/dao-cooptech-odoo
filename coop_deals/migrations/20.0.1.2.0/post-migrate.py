# -*- coding: utf-8 -*-
"""Ответственные сторон у заведённых сделок (решение 450).

У человека — он сам, у организации — первый по стажу держатель «Сделок».
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    deals = env['coop.deal'].with_context(active_test=False).search([])
    deals._coop_fill_responsibles()
    empty = deals.filtered(lambda d: not d.responsible_a_id or not d.responsible_b_id)
    _logger.info('Сделки: ответственные проставлены у %s, без ответственного '
                 'хотя бы у одной стороны %s', len(deals) - len(empty), len(empty))
