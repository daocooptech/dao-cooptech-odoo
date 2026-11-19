# -*- coding: utf-8 -*-
"""Доска «MVP DAO COOPTECH» — проект в управлении нашего проекта.

Владелец 19.11.2026: «почему то не подгружается проект» — страница
«MVP DAO COOPTECH» в «Управлении проектами» без фото, заявок, аналитики и
карты; «да да всё правильно, это проект об этом проекте что мы сейчас с
тобой делаем». Карточка нашего проекта «ДАО КООПТЕХ» (`project_cooptech`)
при запуске 18.11 завела себе пустой проект в управлении, а доска задач
из vault (`.scripts/sync-odoo-board.py`, ищет проект по имени) осталась
ни с чем не связана. Связываем карточку с доской; пустой проект —
в архив (без задач и без другой карточки).
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ours = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    Project = env['project.project'].with_context(active_test=False)
    board = Project.search([('name', '=', 'MVP DAO COOPTECH')], limit=1)
    if not ours or not board or ours.project_id == board:
        return
    old = ours.project_id
    ours.project_id = board
    _logger.info('Наш проект связан с доской «%s» (%s)', board.name, board.id)
    if old and old != board:
        tasks = env['project.task'].with_context(active_test=False).search_count(
            [('project_id', '=', old.id)])
        others = env['coop.project'].search_count([('project_id', '=', old.id)])
        if not tasks and not others:
            old.active = False
            _logger.info('Пустой проект %s в управлении — в архив', old.id)
