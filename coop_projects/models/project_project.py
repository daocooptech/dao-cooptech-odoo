# -*- coding: utf-8 -*-
"""Штатный проект Odoo, дополненный суммой вкладов.

Расширение стояло в модуле вакансий: сумма вкладов понадобилась там
раньше всего — без неё не считалась доля исполнителя. Место было
временным и таким и названо в комментарии, но так и осталось: раздел
вакансий правил чужую модель, а раздел проектов о ней не знал.

Теперь расширение там, где ему место. Вакансии по-прежнему читают сумму,
но уже как потребитель, а не как хозяин.

Переопределение валюты, стоявшее рядом, снято: `project.project` в ядре
объявляет `currency_id` вычисляемым от компании (строка 96 в
`project/models/project_project.py`). Наша копия подменяла его обычным
полем со значением по умолчанию — то есть гасила расчёт ядра ради того
же самого результата.
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Полномочия, с которыми член организации действует от её имени, — те же,
# что у `res.users.ACTING_POWERS` в coop_base.
_ACTING_POWERS = ('publish', 'deal', 'treasury', 'site')


class ProjectProject(models.Model):
    _inherit = 'project.project'

    coop_contribution_total = fields.Monetary(
        string='Сумма вкладов, ₽', currency_field='currency_id',
        help='Денежная оценка всех вкладов в проект: деньгами, ресурсами и '
             'трудом. От неё считается доля каждого участника.')
    coop_project_id = fields.One2many(
        'coop.project', 'project_id', string='Сбор вкладов',
        help='Обратная сторона связи: из какого сбора вырос этот проект. '
             'Пусто у проектов, заведённых напрямую в управлении.')

    # Общие этапы задач: xml-id в coop_projects -> название.
    _COOP_TASK_STAGES = [
        ('task_stage_idea', 'Идея'),
        ('task_stage_doing', 'В работе'),
        ('task_stage_review', 'На проверке'),
        ('task_stage_done', 'Готово'),
    ]

    @api.model
    def coop_adopt_task_stages(self):
        """Признать своими этапы, которые загрузчик завёл по названию.

        Из нескольких одноимённых берётся тот, к которому привязано
        больше проектов, — им и пользуются. Личные этапы (`user_id`) не
        трогаем: это «Входящие / Сегодня» каждого человека.
        """
        Data = self.env['ir.model.data'].sudo()
        Stage = self.env['project.task.type'].sudo().with_context(active_test=False)
        for xmlid, name in self._COOP_TASK_STAGES:
            if self.env.ref('coop_projects.%s' % xmlid, raise_if_not_found=False):
                continue
            found = Stage.search([('name', '=', name), ('user_id', '=', False)])
            if not found:
                continue
            stage = max(found, key=lambda s: (len(s.project_ids), -s.id))
            Data.create({'module': 'coop_projects', 'name': xmlid,
                         'model': 'project.task.type', 'res_id': stage.id})

    @api.model
    def coop_merge_task_stages(self):
        """Слить одноимённые общие этапы в свои.

        На боевой два общих «Готово» (замер копии 08.10.2026: 55 и 119
        проектов, задачи в обоих) — загрузчики заводили этап по названию в
        разное время. Задачи и проекты переезжают в свой этап, дубль — в
        архив. Личные этапы людей не трогаем.
        """
        Stage = self.env['project.task.type'].sudo().with_context(active_test=False)
        Task = self.env['project.task'].sudo().with_context(
            active_test=False, mail_notrack=True, tracking_disable=True)
        merged = 0
        for stage in self._coop_task_stages():
            twins = Stage.search([('id', '!=', stage.id), ('user_id', '=', False)]
                                 ).filtered(lambda s: s.name == stage.name)
            for twin in twins:
                Task.search([('stage_id', '=', twin.id)]).write({'stage_id': stage.id})
                for project in twin.project_ids:
                    project.type_ids = [fields.Command.unlink(twin.id),
                                        fields.Command.link(stage.id)]
                twin.active = False
                merged += 1
        if merged:
            _logger.info('Одноимённые этапы задач слиты в общие: %s', merged)
        return merged

    @api.model
    def _coop_task_stages(self):
        stages = self.env['project.task.type']
        for xmlid, _name in self._COOP_TASK_STAGES:
            stages |= self.env.ref('coop_projects.%s' % xmlid,
                                   raise_if_not_found=False) or stages.browse()
        return stages

    @api.model
    def coop_drop_engine_stages(self):
        """Снять с проектов пустые этапы, которые движок завёл сам.

        Движок 20 каждому новому проекту без этапов заводит свои четыре
        «New / In Progress / Done / Cancelled». У проектов с общими этапами
        они лишние: на канбане восемь столбцов. Снимаем только пустые,
        только принадлежащие одному проекту и без xml-id; сами этапы — в
        архив, а не удаляются.
        """
        shared = self._coop_task_stages()
        if len(shared) < 4:
            return 0
        Stage = self.env['project.task.type'].sudo().with_context(active_test=False)
        Task = self.env['project.task'].sudo().with_context(active_test=False)
        named = set(self.env['ir.model.data'].sudo().search(
            [('model', '=', 'project.task.type')]).mapped('res_id'))
        dropped = Stage
        for project in self.sudo().with_context(active_test=False).search(
                [('type_ids', 'in', shared.ids)]):
            extra = project.type_ids - shared
            extra = extra.filtered(lambda s: (
                not s.user_id and s.id not in named
                and s.project_ids == project
                and not Task.search_count([('stage_id', '=', s.id)])))
            if extra:
                project.type_ids = [fields.Command.unlink(s.id) for s in extra]
                dropped |= extra
        if dropped:
            dropped.write({'active': False})
            _logger.info('Пустые этапы движка сняты с проектов: %s', len(dropped))
        return len(dropped)

    @api.model
    def _coop_partner_users(self, partners):
        """Пользователи, стоящие за участниками: сам человек, а за
        организацию — её действующие члены с полномочием действовать от
        её имени. Только внутренние: портальному команда не откроет
        ничего, а поле команды его и не принимает.
        """
        users = partners.sudo().user_ids
        memberships = self.env['coop.membership'].sudo().search([
            ('organization_id', 'in', partners.ids),
            ('state', '=', 'active'),
            ('power_ids.code', 'in', _ACTING_POWERS),
        ])
        users |= memberships.partner_id.user_ids
        return users.filtered(lambda u: not u.share and u.active)

    def _coop_add_team(self, users):
        """Добавить в команду проекта — только добавить, не заменяя.

        Команда в Odoo 20 и есть доступ к проекту с видимостью
        «followers». Убирать никого не убираем: участника мог добавить
        руками руководитель проекта.
        """
        users = users.filtered(lambda u: not u.share)
        for project in self.sudo():
            missing = users - project.allowed_internal_user_ids
            if missing:
                project.allowed_internal_user_ids = [
                    fields.Command.link(user.id) for user in missing]

    def _coop_sync_team(self):
        """Собрать команду заново: сбор (инициатор и принятые вкладчики),
        исполнители задач, руководитель проекта."""
        Task = self.env['project.task'].sudo().with_context(active_test=False)
        for project in self.sudo():
            users = project.user_id
            for fee in project.coop_project_id:
                users |= fee._project_team_users()
            users |= Task.search([('project_id', '=', project.id)]).user_ids
            project._coop_add_team(users)


class ProjectTask(models.Model):
    _inherit = 'project.task'

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        tasks._coop_assignees_to_team()
        return tasks

    def write(self, vals):
        result = super().write(vals)
        if 'user_ids' in vals or 'project_id' in vals:
            self._coop_assignees_to_team()
        return result

    def _coop_assignees_to_team(self):
        """Исполнитель задачи входит в команду её проекта.

        Иначе он видит задачу, но не проект: у 101 исполнителя настоящих
        проектов не открывался ни один (разбор ux 08.10.2026).
        """
        for task in self.sudo():
            project = task.project_id
            if task.user_ids and project.privacy_visibility == 'followers':
                project._coop_add_team(task.user_ids)
