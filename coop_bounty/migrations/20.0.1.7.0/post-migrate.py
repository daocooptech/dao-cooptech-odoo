# -*- coding: utf-8 -*-
"""Оценка открытых карточек доски нашего проекта — из задач краудсорсинга (№ 485)."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ours = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    if not ours or not ours.project_id:
        return
    tasks = env['project.task'].search([('project_id', '=', ours.project_id.id)])
    _logger.info('Оценка в токенах взята у %s карточек доски', tasks._coop_tokens_adopt())
