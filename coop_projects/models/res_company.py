# -*- coding: utf-8 -*-
"""«Внутренний» проект компании учёта — сразу в архив.

Учёт времени заводит каждой новой компании проект «Внутренний» с
задачами «Обучение» и «Встреча» — для часов вне проектов. На платформе
компания учёта есть у каждой организации, и в «Управлении проектами» у
сотрудника вместо настоящих проектов стояла пустая заглушка; кнопка
«Проекты» кабинета вела в неё же (решение 452: «Внутренние» убрать).

Не удаляем, а архивируем: компания ссылается на проект полем
`internal_project_id`, и учёт времени вправе писать в него часы.
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _create_internal_project_task(self):
        projects = super()._create_internal_project_task()
        projects.sudo().write({'active': False})
        return projects

    @api.model
    def coop_archive_internal_projects(self):
        """Убрать в архив «Внутренние», заведённые до этой правки.

        Только пустые от работы: проект, где уже ведут задачи сверх двух
        шаблонных или пишут часы, — чей-то настоящий, его не трогаем.
        """
        companies = self.sudo().search([('internal_project_id', '!=', False)])
        projects = companies.internal_project_id.filtered('active')
        Task = self.env['project.task'].sudo().with_context(active_test=False)
        Line = self.env['account.analytic.line'].sudo()
        idle = projects.filtered(lambda p: (
            Task.search_count([('project_id', '=', p.id)]) <= 2
            and not Line.search_count([('project_id', '=', p.id)])))
        if idle:
            idle.write({'active': False})
            _logger.info('«Внутренние» проекты в архиве: %s из %s',
                         len(idle), len(projects))
        return len(idle)
