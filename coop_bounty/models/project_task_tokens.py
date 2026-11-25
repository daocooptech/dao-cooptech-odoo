# -*- coding: utf-8 -*-
"""Токены за задачи в «Управлении проектом» (№ 485, решение 698).

Владелец 25.11.2026: «нужно каждой задаче давать оценку в токенах и
начислять тому кто эти задачи выполняет»; «у каждой задачи должен быть
исполнитель, вот ему и начисляются токены». Оценку ставит автор при
создании задачи (решение 549), правило — для всех проектов с токеном.

Начисляет приёмка менеджера проекта, а не сама отметка «Сделано»:
исполнитель, закрывший свою задачу, иначе заплатил бы себе сам. Менеджер
переводит в «Сделано» — это и приёмка; закрыл другой — менеджер жмёт
«Принять и начислить».

Наш проект платит токенами услуг платформы из фонда задач — через задачу
краудсорсинга, с реестром дохода и актом; остальные — своими токенами, в
пределах «Токенов на задачи».
"""
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .coop_bounty_p2 import _tokens

NUMBER_RE = re.compile(r'^(\d+)\.\s')


class CoopProjectTokenMoveTask(models.Model):
    _inherit = 'coop.project.token.move'

    work_task_id = fields.Many2one(
        'project.task', string='Задача в управлении проектом', index=True, ondelete='set null')


class CoopBountyTaskWork(models.Model):
    _inherit = 'coop.bounty.task'

    work_task_id = fields.Many2one(
        'project.task', string='Задача в управлении проектом', index=True,
        ondelete='set null', readonly=True, copy=False)


class ProjectTaskTokens(models.Model):
    _inherit = 'project.task'

    coop_token_on = fields.Boolean(compute='_compute_coop_token_card')
    coop_token_unit = fields.Char(string='Токен', compute='_compute_coop_token_card')
    coop_token_manager = fields.Boolean(compute='_compute_coop_token_card')
    coop_token_can_set = fields.Boolean(compute='_compute_coop_token_card')
    coop_token_state = fields.Char(string='Начисление', compute='_compute_coop_token_state')
    coop_token_waits = fields.Boolean(compute='_compute_coop_token_state')
    coop_tokens = fields.Integer(
        string='Оценка в токенах', tracking=True,
        help='Сколько токенов проекта получит исполнитель, когда менеджер примет задачу. '
             'Ставит автор задачи. Исполнителей несколько — поровну.')
    coop_tokens_paid = fields.Integer(string='Начислено токенов', readonly=True, copy=False)
    coop_tokens_paid_on = fields.Date(string='Когда начислено', readonly=True, copy=False)
    coop_contribution_id = fields.Many2one(
        'coop.project.contribution', string='Учтено вкладом', readonly=True, copy=False,
        index=True, ondelete='set null',
        help='Результат задачи внесён в проект вкладом — токены за неё не начисляются.')

    _coop_tokens_positive = models.Constraint(
        'check(coop_tokens >= 0)', 'Оценка в токенах — не меньше нуля.')

    def _coop_token_card(self):
        """Карточка проекта, чьими токенами оплачивается задача."""
        self.ensure_one()
        card = self.project_id.sudo().coop_project_id[:1]
        return card if card.coop_has_token else card.browse()

    def _coop_token_is_manager(self):
        self.ensure_one()
        return bool(self.project_id) and self.project_id.sudo().user_id == self.env.user

    @api.depends('project_id', 'create_uid', 'coop_tokens_paid', 'coop_contribution_id')
    @api.depends_context('uid')
    def _compute_coop_token_card(self):
        for task in self:
            card = task._coop_token_card()
            task.coop_token_on = bool(card)
            task.coop_token_unit = card._coop_token_unit() if card else False
            task.coop_token_manager = task._coop_token_is_manager()
            task.coop_token_can_set = not task.coop_tokens_paid and not task.coop_contribution_id and (
                not task.create_uid or task.create_uid == self.env.user or task.coop_token_manager)

    def _coop_token_crowd(self):
        """Задача краудсорсинга нашего проекта для этой карточки доски."""
        self.ensure_one()
        Bounty = self.env['coop.bounty.task'].sudo()
        ours = Bounty._coop_our_project()
        if not ours or self._coop_token_card() != ours:
            return Bounty
        found = Bounty.search([('work_task_id', '=', self._origin.id)], limit=1)
        match = NUMBER_RE.match(self.name or '')
        if not found and match and not self.parent_id:
            found = Bounty.search([
                ('project_id', '=', ours.id),
                ('coop_source_ref', '=', 'vault:%s' % match.group(1))], limit=1)
        return found

    @api.depends('state', 'coop_tokens', 'coop_tokens_paid', 'coop_contribution_id', 'user_ids',
                 'project_id')
    def _compute_coop_token_state(self):
        for task in self:
            waits = False
            unit = task.coop_token_unit or ''
            if task.coop_contribution_id:
                text = _('Учтено вкладом в проект — токены не начисляются')
            elif task.coop_tokens_paid:
                text = _('Начислено %(amount)s %(unit)s',
                         amount=_tokens(task.coop_tokens_paid), unit=unit)
            elif not task.coop_token_on or not task.coop_tokens:
                text = False
            elif task.state == '1_done':
                text = _('Ждёт приёмки менеджером проекта')
                waits = True
            else:
                text = _('После приёмки — исполнителю')
            task.coop_token_state = text
            task.coop_token_waits = waits

    # ── Исполнитель есть у каждой задачи ─────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        for task in tasks.sudo():
            if task.user_ids or not task._coop_token_card():
                continue
            # Не назначен — исполнитель старшей задачи, автор или менеджер
            # проекта; системный пользователь исполнителем не бывает.
            author = task.create_uid.filtered(lambda u: u.id != 1 and u.active and not u.share)
            task.user_ids = task.parent_id.user_ids or author or task.project_id.user_id
        for task in tasks:
            if task.state == '1_done':
                task._coop_tokens_accept()
        return tasks

    def write(self, vals):
        if 'coop_tokens' in vals:
            for task in self:
                if task.coop_tokens == vals['coop_tokens']:
                    continue
                if task.coop_tokens_paid or task.coop_contribution_id:
                    raise UserError(_(
                        'Задача «%s» уже рассчитана — оценку не меняют.') % task.name)
                if not self.env.su and task.create_uid != self.env.user \
                        and not task._coop_token_is_manager():
                    raise UserError(_(
                        'Оценку задачи в токенах ставит её автор или менеджер проекта.'))
        before = {}
        if 'user_ids' in vals and not self.env.su:
            before = {task.id: task.user_ids.ids for task in self if task.coop_tokens_paid}
        # Исполнитель не уводит задачу к чужому менеджеру или в другой проект
        # после расчёта: за неё уже заплачено.
        if 'project_id' in vals and self.filtered(
                lambda t: t.coop_tokens_paid and t.project_id.id != vals['project_id']):
            raise UserError(_('За задачу уже начислены токены проекта — в другой не переносят.'))
        result = super().write(vals)
        if 'user_ids' in vals and not self.env.su:
            for task in self:
                if task.id in before and set(before[task.id]) != set(task.user_ids.ids):
                    raise UserError(_(
                        'За задачу «%s» токены уже начислены — исполнителя не меняют.') % task.name)
                if not task.user_ids and task._coop_token_card():
                    raise ValidationError(_(
                        'Укажите исполнителя задачи «%s»: ему начисляются токены проекта.')
                        % task.name)
        if {'state', 'stage_id', 'coop_tokens', 'user_ids'} & set(vals):
            for task in self:
                if task.state == '1_done':
                    task._coop_tokens_accept()
        return result

    # ── Начисление ───────────────────────────────────────────────────────

    def action_coop_tokens_accept(self):
        for task in self:
            if not task._coop_token_is_manager():
                raise UserError(_('Задачу принимает менеджер проекта.'))
            if task.state != '1_done':
                raise UserError(_('Принять можно сделанную задачу.'))
            reason = task._coop_tokens_accrue()
            if reason:
                raise UserError(reason)
        return True

    def _coop_tokens_accept(self):
        """Задача сделана: менеджер перевёл — значит принял."""
        for task in self:
            if task._coop_token_is_manager():
                reason = task._coop_tokens_accrue()
                if reason:
                    task.sudo().message_post(body=_('Токены не начислены. %s') % reason)

    def _coop_tokens_accrue(self):
        """Начислить исполнителям. Возвращает причину отказа или False."""
        self.ensure_one()
        task = self.sudo()
        # Второй щелчок или вторая вкладка не начислят дважды.
        self.env.flush_all()
        self.env.cr.execute('SELECT id FROM project_task WHERE id = %s FOR UPDATE', [task.id])
        task.invalidate_recordset(['coop_tokens_paid', 'coop_contribution_id'])
        card = task._coop_token_card()
        if not card or task.coop_tokens_paid or task.coop_contribution_id or not task.coop_tokens:
            return False
        partners = task.user_ids.partner_id
        if not partners:
            return _('У задачи «%s» нет исполнителя.') % task.name
        # Поровну; остаток от деления — по токену первым.
        part, rest = divmod(task.coop_tokens, len(partners))
        plan = [(p, part + (1 if n < rest else 0)) for n, p in enumerate(partners)]
        plan = [(p, amount) for p, amount in plan if amount]
        try:
            with self.env.cr.savepoint():
                if card == self.env['coop.bounty.task']._coop_our_project():
                    paid = task._coop_tokens_from_fund(card, plan)
                else:
                    paid = task._coop_tokens_from_project(card, plan)
        except UserError as error:
            # Откат точки сохранения — и кэш за ним.
            self.env.invalidate_all(flush=False)
            return str(error)
        task.write({'coop_tokens_paid': paid,
                    'coop_tokens_paid_on': self.env.context.get('coop_token_date')
                    or fields.Date.context_today(task)})
        task.message_post(body=_('Задача принята, начислено: %s.') % ', '.join(
            '%s — %s %s' % (p.display_name, _tokens(amount), card._coop_token_unit())
            for p, amount in plan))
        return False

    def _coop_tokens_from_project(self, card, plan):
        self.ensure_one()
        card.invalidate_recordset(['coop_bounty_blocked', 'coop_bounty_paid', 'coop_bounty_free'])
        need = sum(amount for _partner, amount in plan)
        if card.coop_bounty_free < need:
            raise UserError(_(
                'Не хватает токенов проекта на задачи: нужно %(need)s %(unit)s, свободно %(free)s.',
                need=_tokens(need), unit=card._coop_token_unit(),
                free=_tokens(card.coop_bounty_free)))
        self.env['coop.project.token.move'].sudo().create([{
            'project_id': card.id, 'partner_id': partner.id, 'amount': amount,
            'work_task_id': self.id,
            'date': self.env.context.get('coop_token_date') or fields.Date.context_today(self),
            'description': _('Задача «%s»') % self.name,
        } for partner, amount in plan])
        return need

    def _coop_tokens_from_fund(self, card, plan):
        """Токены услуг платформы: фонд, выплата, реестр дохода — те же, что
        у задач краудсорсинга."""
        self.ensure_one()
        Bounty = self.env['coop.bounty.task'].sudo().with_context(tracking_disable=True)
        bounty = self._coop_token_crowd()
        if bounty and bounty.state in ('assigned', 'submitted', 'dispute', 'accepted'):
            raise UserError(_(
                'Эту задачу взяли в краудсорсинге — её принимают и оплачивают там.'))
        need = sum(amount for _partner, amount in plan)
        method = self.env['coop.bounty.method'].sudo().search([('code', '=', 'tokens')], limit=1)
        match = NUMBER_RE.match(self.name or '')
        today = fields.Date.context_today(self)
        if bounty:
            # Сумму в резерве не меняют: через черновик, резерв — заново.
            bounty.write({'state': 'draft'})
            bounty.write({'reward_tokens': need})
        else:
            bounty = Bounty.with_context(mail_create_nolog=True).create({
                'name': NUMBER_RE.sub('', self.name),
                'payer_id': self.env.company.partner_id.id,
                'project_id': card.id,
                'reward_tokens': need,
                'manager_id': self.project_id.user_id.id or self.env.uid,
                'coop_source_ref': 'vault:%s' % match.group(1)
                if match and not self.parent_id else False,
                'criterion_ids': [(0, 0, {
                    'name': _('Результат соответствует описанию задачи'), 'done': True})],
            })
        bounty.allowed_method_ids = [(6, 0, method.ids)]
        self.env.invalidate_all()
        bounty._coop_reserve_fund()
        bounty.application_ids.filtered(lambda a: a.state == 'applied').write({'state': 'rejected'})
        bounty.write({'work_task_id': self.id, 'payment_mode': 'tokens', 'state': 'assigned',
                      'assignee_id': plan[0][0].id, 'assigned_on': today})
        for partner, amount in plan:
            bounty.assignee_id = partner
            bounty._coop_pay(amount=amount)
        bounty.criterion_ids.write({'done': True})
        bounty.write({'state': 'accepted', 'assignee_id': plan[0][0].id, 'submitted_on': today,
                      'accepted_on': today, 'paid_amount': bounty.paid_amount + need})
        return need

    def _coop_tokens_adopt(self):
        """Оценку открытых карточек нашей доски взять из их задач краудсорсинга."""
        done = 0
        for task in self.sudo():
            if task.coop_tokens or task.state in ('1_done', '1_canceled') or task.parent_id:
                continue
            bounty = task._coop_token_crowd()
            if bounty and bounty.state in ('draft', 'published'):
                task.with_context(tracking_disable=True).coop_tokens = bounty.reward_tokens
                done += 1
        return done


class CoopProjectWorkTokens(models.Model):
    """Начисленное за задачи в управлении проектом — из тех же «Токенов на
    задачи», что и краудсорсинг."""
    _inherit = 'coop.project'

    def _compute_coop_bounty_reserve(self):
        super()._compute_coop_bounty_reserve()
        paid = {project.id: amount for project, amount in
                self.env['coop.project.token.move'].sudo()._read_group(
                    [('project_id', 'in', self._origin.ids), ('work_task_id', '!=', False)],
                    ['project_id'], ['amount:sum'])}
        for project in self:
            extra = paid.get(project._origin.id, 0)
            project.coop_bounty_paid += extra
            if project.coop_bounty_token_limit:
                project.coop_bounty_free -= extra


class ProjectProjectTokens(models.Model):
    _inherit = 'project.project'

    coop_an_tokens = fields.Html(
        string='Токены за задачи', compute='_compute_coop_an_tokens', sanitize=False)

    def _compute_coop_an_tokens(self):
        """Кому и сколько начислено за задачи проекта; что ещё предстоит."""
        from odoo.addons.coop_projects.models.coop_project import analytics_html
        Task = self.env['project.task'].sudo()
        for project in self:
            card = project.sudo().coop_project_id[:1]
            if not card.coop_has_token:
                project.coop_an_tokens = False
                continue
            unit = card._coop_token_unit()
            tasks = Task.search([('project_id', '=', project.id), ('coop_tokens', '>', 0),
                                 ('coop_contribution_id', '=', False)])
            paid = tasks.filtered('coop_tokens_paid')
            waits = tasks.filtered('coop_token_waits')
            ahead = tasks.filtered(lambda t: t.state not in ('1_done', '1_canceled')
                                   and not t.coop_tokens_paid)
            rows = {}
            for task in tasks:
                users = task.user_ids
                for index, user in enumerate(users):
                    row = rows.setdefault(user.partner_id.display_name, [0, 0, 0])
                    part, rest = divmod(task.coop_tokens, len(users))
                    share = part + (1 if index < rest else 0)
                    if task in paid:
                        row[0] += 1
                        row[1] += share
                    elif task in ahead:
                        row[2] += share
            table = [(name, str(row[0]), _tokens(row[1]), _tokens(row[2]))
                     for name, row in sorted(rows.items(), key=lambda item: -item[1][1])]
            project.coop_an_tokens = analytics_html(
                stats=[(_('Начислено, %s') % unit, _tokens(sum(paid.mapped('coop_tokens_paid')))),
                       (_('Задач оплачено'), str(len(paid))),
                       (_('Ждут приёмки'), str(len(waits))),
                       (_('Оценка открытых задач, %s') % unit,
                        _tokens(sum(ahead.mapped('coop_tokens'))))] if tasks else [],
                table=([_('Исполнитель'), _('Задач'), _('Начислено'), _('В открытых')], table),
                empty=_('Задач с оценкой в токенах пока нет.'))
