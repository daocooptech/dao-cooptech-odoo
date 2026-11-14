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

from odoo import _, api, fields, models
from odoo.exceptions import UserError

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

    coop_offer_new = fields.Integer(
        string='Новых заявок', compute='_compute_coop_offers')
    coop_offer_can = fields.Boolean(
        string='Разбирает заявки', compute='_compute_coop_offers')

    @api.depends('coop_project_id.new_offer_count',
                 'coop_project_id.coop_is_team')
    def _compute_coop_offers(self):
        """Заявки на вклады — кнопка в управлении проектом тем, кто вправе
        их разбирать: команде сбора, из которого вырос проект."""
        for project in self:
            sources = project.coop_project_id.filtered('coop_is_team')
            project.coop_offer_can = bool(sources)
            project.coop_offer_new = sum(sources.mapped('new_offer_count'))

    coop_offers_json = fields.Json(
        string='Заявки на потребности', compute='_compute_coop_offers_json')
    coop_summary = fields.Html(
        string='Сводка', compute='_compute_coop_summary', sanitize=False)

    coop_an_money = fields.Html(
        string='Финансовые вклады', compute='_compute_coop_analytics',
        sanitize=False)
    coop_an_intangibles = fields.Html(
        string='НМА', compute='_compute_coop_analytics', sanitize=False)
    coop_an_cfa = fields.Html(
        string='ЦФА', compute='_compute_coop_analytics', sanitize=False)
    coop_an_deals = fields.Html(
        string='Контракты', compute='_compute_coop_analytics', sanitize=False)

    @api.depends('coop_project_id.contribution_ids.state',
                 'coop_project_id.contribution_ids.need_id',
                 'coop_project_id.coop_is_team')
    def _compute_coop_offers_json(self):
        """Разбор заявок на потребности — данные для страницы управления
        (образец `OffersReviewPage`, задача 395): слева потребности со
        счётчиками, справа карточки заявок выбранной."""
        contribution = self.env['coop.project.contribution']
        kinds = dict(contribution._fields['kind']._description_selection(self.env))
        forms = dict(contribution._fields['labour_form']._description_selection(self.env))
        for project in self:
            source = project.coop_project_id.filtered('coop_is_team')[:1]
            if not source:
                project.coop_offers_json = False
                continue
            offers = source.contribution_ids.filtered('need_id')
            needs = source.need_ids | offers.mapped('need_id')
            out_needs, out_offers = [], []
            for need in needs.sorted('id'):
                mine = offers.filtered(lambda c: c.need_id == need)
                accepted = need.need_accepted_id
                out_needs.append({
                    'id': need.id,
                    'name': need.name,
                    'price': need.price_display or '',
                    'new': len(mine.filtered(lambda c: c.state == 'offered')),
                    'total': len(mine),
                    'closed': bool(accepted),
                    'closed_by': accepted.partner_id.name if accepted else '',
                })
            for c in offers.sorted(lambda c: (c.state != 'offered', -(c.id or 0))):
                out_offers.append({
                    'id': c.id,
                    'need_id': c.need_id.id,
                    'partner': c.partner_id.name,
                    'partner_id': c.partner_id.id,
                    'trust': c.partner_trust,
                    'deals': c.partner_deals_done,
                    'value': c.value,
                    'currency': c.currency_id.symbol or '',
                    'need_price': c.need_price,
                    'diff': c.value_diff,
                    'diff_label': c.value_diff_label or '',
                    'kind': kinds.get(c.kind, ''),
                    'name': c.name or '',
                    'labour_form': forms.get(c.labour_form, '') if c.labour_form else '',
                    'offered_on': fields.Date.to_string(c.offered_on) if c.offered_on else '',
                    'state': c.state,
                    'share': c.share_percent,
                })
            project.coop_offers_json = {'needs': out_needs, 'offers': out_offers}

    @api.depends('coop_project_id.new_offer_count', 'task_count',
                 'closed_task_count', 'milestone_count',
                 'milestone_count_reached', 'last_update_status')
    def _compute_coop_summary(self):
        """«Сводка» образца 395: статус, заявки, задачи, вехи, табели."""
        status = dict(self._fields['last_update_status']._description_selection(self.env))
        for project in self:
            source = project.coop_project_id.filtered('coop_is_team')[:1]
            rows = [(_('Статус'), status.get(project.last_update_status, ''))]
            if source:
                total = len(source.contribution_ids.filtered('need_id'))
                rows.append((_('Заявки'), _('%(n)s новых · %(t)s', n=source.new_offer_count, t=total)))
            rows.append((_('Задачи'), '%s / %s' % (project.closed_task_count, project.task_count)))
            rows.append((_('Вехи'), '%s / %s' % (project.milestone_count_reached, project.milestone_count)))
            if 'total_timesheet_time' in project._fields:
                rows.append((_('Табели'), '%s ч' % int(project.total_timesheet_time or 0)))
            project.coop_summary = '<dl class="o_coop_pm_sum">%s</dl>' % ''.join(
                '<dt>%s</dt><dd>%s</dd>' % (name, value) for name, value in rows)

    @api.depends('coop_project_id')
    def _compute_coop_analytics(self):
        """Аналитика сбора на странице управления — четыре переключателя
        образца 395. Блоки дают модули, что есть в базе; здесь их берём."""
        names = {'coop_an_money': 'analytics_money',
                 'coop_an_intangibles': 'analytics_intangibles',
                 'coop_an_cfa': 'analytics_cfa',
                 'coop_an_deals': 'analytics_deals'}
        for project in self:
            source = project.coop_project_id[:1]
            for mine, theirs in names.items():
                project[mine] = (source[theirs]
                                 if source and theirs in source._fields
                                 else False)

    def action_coop_open_offers(self):
        """Разбор заявок на потребности — из управления проектом: тот же
        канбан, что со страницы сбора (`coop.project.action_open_offers`)."""
        self.ensure_one()
        source = self.coop_project_id.filtered('coop_is_team')[:1]
        if not source:
            raise UserError(_('Заявки разбирает команда проекта.'))
        return source.action_open_offers()

    def action_coop_new_task(self):
        """Главная кнопка шапки «Задача» (образец WorkHeaderD, задача 449):
        новая задача этого проекта."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Новая задача'),
            'res_model': 'project.task',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
            'context': {'default_project_id': self.id},
        }

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
