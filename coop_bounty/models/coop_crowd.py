# -*- coding: utf-8 -*-
"""Краудсорсинг для всех проектов (решение 690).

Задачи проекта оплачиваются только токенами этого проекта: у нашего
проекта (ДАО КООПТЕХ) это токены услуг платформы из фонда задач, у
остальных — их собственные токены. Экономику своего токена каждый
проект раскрывает сам, в рамках законов своей страны; платформа общих
правил токена проекта не задаёт. Учёт токенов проекта — в базе узла,
как и токенов за задачи платформы (решение 668).
"""
import json
import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import file_path

from .coop_bounty import RESERVED_STATES

_logger = logging.getLogger(__name__)

# Второй критерий задачи нашего проекта — по специализации; у
# остальных (код) — автотесты и сервер.
CRITERIA_BY_SPECIALIZATION = {
    'Юрисконсульт': 'Разбор записан со ссылками на статьи закона и пункты решений',
    'Бухгалтерия': 'Проводки и отчёты проверены на примере из базы платформы',
    'Аналитика, Data Science': 'Цифры воспроизводятся запросом к базе узла',
    'Бизнес-консультант': 'Расчёт и выводы оформлены документом, исходные цифры приложены',
    'Дизайн, графика': 'Экран сверен с дизайн-системой платформы',
    'Переводчик': 'Строки интерфейса вычитаны на экране, английских слов не осталось',
}


# Задачи, видные всем: черновик — дело автора, отменённая — уже не задача.
CROWD_VISIBLE = RESERVED_STATES + ('accepted',)


class CoopProjectToken(models.Model):
    _inherit = 'coop.project'

    coop_bounty_task_ids = fields.One2many(
        'coop.bounty.task', 'project_id', string='Задачи краудсорсинга',
        domain=[('state', 'in', CROWD_VISIBLE)])
    coop_crowd_open_count = fields.Integer(string='Открыто задач',
                                           compute='_compute_coop_crowd_counts')
    coop_crowd_work_count = fields.Integer(string='В работе',
                                           compute='_compute_coop_crowd_counts')
    coop_crowd_done_count = fields.Integer(string='Принято',
                                           compute='_compute_coop_crowd_counts')
    coop_crowd_open_tokens = fields.Integer(string='Токенов за открытые задачи',
                                            compute='_compute_coop_crowd_counts')
    coop_is_cooptech = fields.Boolean(compute='_compute_coop_is_cooptech')

    def _compute_coop_crowd_counts(self):
        # Суммы и счёт — по всем видимым задачам, через sudo: чужой
        # черновик в счёт не входит, а права на чтение опубликованных
        # есть у всех.
        groups = self.env['coop.bounty.task'].sudo()._read_group(
            [('project_id', 'in', self.ids), ('state', 'in', CROWD_VISIBLE)],
            ['project_id', 'state'], ['__count', 'reward_tokens:sum'])
        stats = {}
        for project, state, count, tokens in groups:
            stats.setdefault(project.id, {})[state] = (count, tokens)
        for project in self:
            own = stats.get(project.id, {})
            project.coop_crowd_open_count = own.get('published', (0, 0))[0]
            project.coop_crowd_open_tokens = own.get('published', (0, 0))[1]
            project.coop_crowd_work_count = sum(
                own.get(state, (0, 0))[0] for state in ('assigned', 'submitted', 'dispute'))
            project.coop_crowd_done_count = own.get('accepted', (0, 0))[0]

    def _compute_coop_is_cooptech(self):
        ours = self.env['coop.bounty.task']._coop_our_project()
        for project in self:
            project.coop_is_cooptech = bool(ours) and project == ours

    def action_coop_crowd_card(self):
        """Карточка проекта по краудсорсингу: токен, экономика, задачи."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'coop.project',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('coop_bounty.view_coop_project_crowd_form').id, 'form')],
            'target': 'current',
        }

    def action_coop_crowd_tasks(self):
        """Все задачи проекта списком — оттуда карточка задачи."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('coop_bounty.action_coop_bounty_task')
        action.update({
            'name': _('Задачи — %s') % self.name,
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id, 'search_default_open': 1},
        })
        return action

    def action_coop_open_project_page(self):
        """Обычная страница проекта — сбор, участие, лента."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'coop.project',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    @api.model
    def _coop_action_help_project(self):
        """«Помощь проекту» — карточка нашего проекта (решение 690)."""
        ours = self.env['coop.bounty.task']._coop_our_project()
        if not ours:
            raise UserError(_('Наш проект в краудсорсинге не заведён.'))
        action = ours.action_coop_crowd_card()
        action['name'] = _('Помощь проекту')
        return action

    coop_token_name = fields.Char(
        string='Токен проекта',
        help='Как проект называет свой токен. Им оплачиваются задачи проекта в краудсорсинге.')
    coop_token_symbol = fields.Char(string='Обозначение', help='Коротко, до шести знаков.')
    coop_token_economy = fields.Html(
        string='Экономика токена',
        help='Что даёт токен, чем обеспечен, как погашается. Проект раскрывает это сам — '
             'в рамках законов своей страны.')
    coop_token_issued = fields.Integer(string='Начислено за задачи, токенов',
                                       compute='_compute_coop_token_issued')

    def _compute_coop_token_issued(self):
        Move = self.env['coop.project.token.move'].sudo()
        Task = self.env['coop.bounty.task'].sudo()
        ours = Task._coop_our_project()
        for project in self:
            if not project.id:
                project.coop_token_issued = 0
            elif project == ours:
                # Наш проект платит токенами услуг платформы — движениями
                # кошелька, а не начислениями токенов проекта.
                project.coop_token_issued = sum(Task.search(
                    [('project_id', '=', project.id), ('state', '=', 'accepted')]).mapped('reward_tokens'))
            else:
                project.coop_token_issued = sum(Move.search(
                    [('project_id', '=', project.id)]).mapped('amount'))

    def _coop_token_unit(self):
        self.ensure_one()
        return self.coop_token_symbol or _('токенов проекта')


class CoopProjectTokenMove(models.Model):
    """Начисление токенов проекта за принятую задачу — учёт в узле."""
    _name = 'coop.project.token.move'
    _description = 'Начисление токенов проекта'
    _order = 'date desc, id desc'

    project_id = fields.Many2one('coop.project', string='Проект', required=True,
                                 index=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Кому', required=True, index=True)
    amount = fields.Integer(string='Токенов', required=True)
    task_id = fields.Many2one('coop.bounty.task', string='Задача', index=True, ondelete='set null')
    date = fields.Date(string='Когда', required=True, default=fields.Date.context_today)
    description = fields.Char(string='За что')


class CoopBountyTaskCrowd(models.Model):
    _inherit = 'coop.bounty.task'

    payment_label = fields.Char(string='Оплата', compute='_compute_payment_label')
    token_unit = fields.Char(compute='_compute_payment_label')
    coop_source_ref = fields.Char(
        string='Номер в списке задач платформы', readonly=True, index=True, copy=False,
        help='Задача нашего проекта, взятая из списка задач платформы: по номеру '
             'список и краудсорсинг сверяются при обновлении модуля.')

    @api.depends('payer_kind', 'project_id.coop_token_name', 'project_id.coop_token_symbol')
    def _compute_payment_label(self):
        for task in self:
            if task.payer_kind == 'platform':
                task.payment_label = _('Токены услуг платформы')
                task.token_unit = _('токенов')
            elif task.project_id:
                task.payment_label = task.project_id.coop_token_name or (
                    _('Токены проекта «%s»') % task.project_id.name)
                task.token_unit = task.project_id._coop_token_unit()
            else:
                task.payment_label = _('Токены проекта')
                task.token_unit = _('токенов проекта')

    def action_coop_open_card(self):
        """Плитка задачи в карточке проекта — полная карточка задачи."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'coop.bounty.task',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    @api.model
    def _coop_our_project(self):
        return self.env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)

    def _coop_check_publishable(self):
        """Только токены своего проекта (решение 690): способ ставится сам."""
        self.ensure_one()
        if self.payer_kind == 'platform':
            code = 'tokens'
            if not self.project_id:
                self.project_id = self._coop_our_project()
        else:
            code = 'project_tokens'
            if not self.project_id:
                raise UserError(_('Укажите проект: задачи краудсорсинга оплачиваются токенами проекта.'))
            if not self.project_id.coop_token_name:
                raise UserError(_(
                    'Сначала опишите токен проекта «%s» — название и экономику токена, '
                    'вкладка «Токен проекта» в карточке проекта.') % self.project_id.name)
        method = self.env['coop.bounty.method'].sudo().search([('code', '=', code)], limit=1)
        self.write({'allowed_method_ids': [(6, 0, method.ids)], 'share_percent': 0})
        return super()._coop_check_publishable()

    # ── Задачи нашего проекта из списка задач платформы (решение 690) ──

    @api.model
    def _coop_sync_cooptech_tasks(self):
        """Открытые задачи из списка платформы — в нашем проекте за токены.

        Список снимает `tools/vault_tasks.py` в `data/cooptech_tasks.json`.
        Новые задачи публикуются с резервом в фонде (без рассылки по
        подпискам: девяносто извещений разом — не новость, а шум); у
        открытых обновляются название и описание; открытая задача, которой
        в списке больше нет, снимается — резерв возвращается в фонд.
        """
        project = self._coop_our_project()
        fund = self.env['coop.bounty.fund'].sudo()._coop_current()
        if not project or not fund:
            return 0
        with open(file_path('coop_bounty/data/cooptech_tasks.json'), encoding='utf-8') as handle:
            rows = json.load(handle)
        Task = self.sudo().with_context(mail_create_nolog=True, tracking_disable=True)
        method = self.env['coop.bounty.method'].sudo().search([('code', '=', 'tokens')], limit=1)
        manager = self.env.ref('base.user_admin', raise_if_not_found=False)
        Spec = self.env['coop.specialization'].sudo()
        existing = {task.coop_source_ref: task for task in Task.search(
            [('coop_source_ref', '!=', False), ('project_id', '=', project.id)])}
        created = 0
        for row in rows:
            ref = 'vault:%s' % row['ref']
            description = Markup('<p>%s</p><p>%s</p>') % (
                row['summary'], _('Задача № %s из списка задач платформы ДАО КООПТЕХ.') % row['ref'])
            task = existing.pop(ref, None)
            if task:
                if task.state in ('draft', 'published'):
                    task.write({'name': row['name'], 'description': description})
                continue
            spec = Spec.search([('name', '=', row['specialization'])], limit=1)
            criteria = [_('Результат соответствует описанию задачи'),
                        CRITERIA_BY_SPECIALIZATION.get(
                            row['specialization'],
                            _('Изменения прошли автотесты и работают на сервере платформы'))]
            task = Task.create({
                'name': row['name'],
                'description': description,
                'payer_id': self.env.company.partner_id.id,
                'project_id': project.id,
                'reward_tokens': row['reward'],
                'allowed_method_ids': [(6, 0, method.ids)],
                'coop_specialization_id': spec.id,
                'manager_id': manager.id if manager else self.env.uid,
                'coop_source_ref': ref,
                'criterion_ids': [(0, 0, {'name': text, 'sequence': (n + 1) * 10})
                                  for n, text in enumerate(criteria)],
            })
            try:
                with self.env.cr.savepoint():
                    task._coop_check_publishable()
                    task._coop_reserve_fund()
                    task.state = 'published'
            except UserError as error:
                # Фонда не хватило — задача ждёт черновиком, остальные идут.
                _logger.warning('Задача %s осталась черновиком: %s', ref, error)
            created += 1
        # Ушла из списка (сделана или снята) — открытую снимаем.
        for task in existing.values():
            if task.state == 'published' and not task.assignee_id:
                task.action_cancel()
        _logger.info('Наш проект: задач из списка платформы заведено %s', created)
        return created
