# -*- coding: utf-8 -*-
"""Улучшения П2, первый кусок (№ 465; решения 671, 690).

- Каждая выплата — запись. Через выплаты считаются фонд, реестр доходов
  в натуральной форме и выполненные задачи — одинаково для одного
  исполнителя, команды, частичной оплаты и постоянной задачи.
- Шкала «частично — N %» задаётся до публикации (как таблицы наград
  Immunefi и HackerOne) и после публикации не пересматривается.
- Несколько исполнителей с делением суммы (Dework): результат за команду
  сдаёт исполнитель задачи — первый утверждённый.
- Постоянная задача: результат сдаёт любой участник без заявки, каждый
  принятый оплачивается, пока не исчерпан лимит (Dework «много сдач»).
- Спор по инициативе исполнителя (посредничество HackerOne и Immunefi).
- Медиана суммы и время ответа автора — на виду.

Способа оплаты у выплаты нет (решение 690): задача платформы платит
токенами услуг платформы из фонда задач, задача проекта — токенами
своего проекта.
"""
from datetime import timedelta
from statistics import median

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .coop_bounty import DISPUTE_AFTER_DAYS

# Сколько возвратов на доработку исполнитель терпит молча: «больше двух
# раз» — с третьего возврата он может открыть спор сам.
RETURNS_BEFORE_DISPUTE = 2
# Сколько дней после отмены задачи со сданным результатом исполнитель
# может открыть спор — столько же, сколько автор может молчать.
CANCEL_DISPUTE_DAYS = DISPUTE_AFTER_DAYS
# Медиана по одной-двум задачам — не медиана, а случай.
MEDIAN_MIN = 3
# Условия оплаты, которые после публикации не меняются: под них уже
# подали заявки и отложили резерв.
P2_TERMS = ('partial_percent', 'is_recurring', 'repeat_limit', 'executor_limit')


def _tokens(value):
    return '{:,}'.format(int(value)).replace(',', ' ')


class CoopBountyPayout(models.Model):
    """Выплата по задаче — одна запись на получателя."""
    _name = 'coop.bounty.payout'
    _description = 'Выплата по задаче'
    _order = 'date desc, id desc'

    task_id = fields.Many2one('coop.bounty.task', string='Задача', required=True,
                              ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Кому', required=True, index=True)
    amount = fields.Integer(string='Токенов', required=True)
    partial = fields.Boolean(string='Частично')
    date = fields.Date(string='Когда', required=True, default=fields.Date.context_today)
    submission_id = fields.Many2one('coop.bounty.submission', string='Сдача', ondelete='set null')
    transaction_id = fields.Many2one(
        'coop.token.transaction', string='Движение токенов платформы', readonly=True)
    token_move_id = fields.Many2one(
        'coop.project.token.move', string='Начисление токенов проекта', readonly=True)
    payer_kind = fields.Selection(related='task_id.payer_kind', store=True)
    project_id = fields.Many2one(related='task_id.project_id', store=True)
    token_unit = fields.Char(related='task_id.token_unit', string='Токен')

    _amount_positive = models.Constraint('check(amount > 0)', 'Выплата — больше нуля токенов.')


class CoopBountyMember(models.Model):
    """Исполнитель в команде и его доля суммы.

    Доли пусты — сумма делится поровну. Результат за команду сдаёт
    исполнитель задачи (первый утверждённый): одна сдача на команду, как
    одна подпись под актом.
    """
    _name = 'coop.bounty.member'
    _description = 'Исполнитель в команде'
    _order = 'id'

    task_id = fields.Many2one('coop.bounty.task', string='Задача', required=True,
                              ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Исполнитель', required=True, index=True)
    share_percent = fields.Float(
        string='Доля суммы, %', digits=(5, 2),
        help='Пусто у всех — сумма делится поровну. Иначе доли в сумме дают 100 %.')
    is_lead = fields.Boolean(string='Сдаёт за команду', compute='_compute_is_lead')

    _one_per_task = models.Constraint('unique(task_id, partner_id)',
                                      'Этот исполнитель уже в команде.')

    @api.depends('task_id.assignee_id', 'partner_id')
    def _compute_is_lead(self):
        for member in self:
            member.is_lead = member.partner_id == member.task_id.assignee_id


class CoopBountySubmissionP2(models.Model):
    _inherit = 'coop.bounty.submission'

    date = fields.Date(string='Сдано', default=fields.Date.context_today, index=True)
    payout_ids = fields.One2many('coop.bounty.payout', 'submission_id', string='Выплата')

    def action_accept_result(self):
        """Принять результат постоянной задачи — и сразу оплатить его."""
        for sub in self:
            task = sub.task_id
            task.check_access('write')
            if not task.is_recurring:
                raise UserError(_('Принимать отдельные сдачи можно только у постоянной задачи.'))
            if sub.state != 'review':
                raise UserError(_('Эта сдача уже проверена.'))
            if task.state != 'published' or task.repeat_done >= task.repeat_limit:
                raise UserError(_('Лимит оплаченных результатов исчерпан.'))
            today = fields.Date.context_today(sub)
            task = task.sudo()
            sub.sudo().write({'state': 'accepted', 'reviewed_on': today})
            payouts = task._coop_pay(submission=sub)
            paid = sum(payouts.mapped('amount'))
            task.write({'paid_amount': task.paid_amount + paid})
            task.message_post(body=_('Принят результат: %(who)s, начислено %(amount)s %(unit)s.',
                                     who=sub.partner_id.display_name, amount=_tokens(paid),
                                     unit=task.token_unit))
            self.env['coop.notification'].sudo()._notify(
                sub.partner_id,
                _('Ваш результат по задаче «%(name)s» принят, начислено %(amount)s %(unit)s.',
                  name=task.name, amount=_tokens(paid), unit=task.token_unit),
                record=task, kind='other')
            if task.repeat_done >= task.repeat_limit:
                task._coop_close_recurring()
            (sub.partner_id | task.payer_id).sudo()._coop_recompute_deal_stats()
        return True

    def action_return_result(self):
        self.ensure_one()
        self.task_id.check_access('write')
        if self.state != 'review':
            raise UserError(_('Эта сдача уже проверена.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Вернуть результат'),
            'res_model': 'coop.bounty.return',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_task_id': self.task_id.id, 'default_submission_id': self.id},
        }


class CoopBountyTaskP2(models.Model):
    _inherit = 'coop.bounty.task'

    # п. 6 — шкала оплаты заранее
    partial_percent = fields.Integer(
        string='Частичный результат, % суммы', default=0, tracking=True,
        help='Сколько платится, если результат принят частично. 0 — частичной оплаты нет. '
             'Задаётся до публикации; в споре администратор выбирает «полностью» или «частично».')
    paid_amount = fields.Integer(string='Выплачено, токенов', readonly=True)
    accepted_partially = fields.Boolean(string='Принято частично', readonly=True)
    payout_ids = fields.One2many('coop.bounty.payout', 'task_id', string='Выплаты')

    # п. 8 — несколько исполнителей
    executor_limit = fields.Integer(
        string='Сколько исполнителей', default=1, tracking=True,
        help='Больше одного — команда: сумма делится поровну или долями, которые задаёт автор; '
             'результат за команду сдаёт первый утверждённый исполнитель.')
    member_ids = fields.One2many('coop.bounty.member', 'task_id', string='Команда')
    member_count = fields.Integer(string='В команде', compute='_compute_member_count')

    # п. 9 — постоянная задача
    is_recurring = fields.Boolean(
        string='Постоянная задача', tracking=True,
        help='Сдать результат может любой участник без заявки; каждый принятый результат '
             'оплачивается, пока не исчерпан лимит.')
    repeat_limit = fields.Integer(string='Сколько результатов оплатить', default=1, tracking=True)
    repeat_done = fields.Integer(string='Оплачено результатов', compute='_compute_repeat_done')
    can_submit_recurring = fields.Boolean(compute='_compute_can_submit_recurring')

    # п. 14 — спор от исполнителя
    dispute_by = fields.Selection([
        ('silence', 'Автор молчит после сдачи'),
        ('executor', 'Исполнитель'),
    ], string='Кто открыл спор', readonly=True)
    dispute_reason = fields.Text(string='В чём спор', readonly=True)
    cancelled_on = fields.Date(string='Отменена', readonly=True)
    cancel_by_arbiter = fields.Boolean(readonly=True)
    returned_count = fields.Integer(string='Возвратов на доработку', compute='_compute_returned_count')
    can_open_dispute = fields.Boolean(compute='_compute_can_open_dispute')

    # пп. 5, 15 — медиана суммы и время ответа автора
    median_hint = fields.Char(string='Обычно за такие задачи', compute='_compute_median_hint')
    payer_answer_label = fields.Char(string='Автор отвечает', compute='_compute_payer_answer_label')
    answer_due = fields.Date(string='Автор ответит до', compute='_compute_answer_due')

    @api.constrains('partial_percent', 'executor_limit', 'repeat_limit', 'is_recurring')
    def _check_p2_limits(self):
        for task in self:
            if not 0 <= task.partial_percent < 100:
                raise ValidationError(_('Частичный результат — от 1 до 99 % суммы, или 0, если его нет.'))
            if not 1 <= task.executor_limit <= 10:
                raise ValidationError(_('Исполнителей — от одного до десяти.'))
            if task.repeat_limit < 1:
                raise ValidationError(_('Оплатить можно хотя бы один результат.'))
            if task.is_recurring and task.executor_limit > 1:
                raise ValidationError(_('У постоянной задачи команды нет: каждый сдаёт и получает сам.'))

    @api.depends('member_ids')
    def _compute_member_count(self):
        for task in self:
            task.member_count = len(task.member_ids)

    @api.depends('is_recurring', 'submission_ids.state')
    def _compute_repeat_done(self):
        for task in self:
            task.repeat_done = len(task.sudo().submission_ids.filtered(
                lambda s: s.state == 'accepted')) if task.is_recurring else 0

    @api.depends('is_recurring', 'state', 'repeat_done', 'repeat_limit', 'payer_id')
    @api.depends_context('uid')
    def _compute_can_submit_recurring(self):
        for task in self:
            task.can_submit_recurring = bool(task.id and not task._coop_recurring_block())

    @api.depends('submission_ids.state')
    def _compute_returned_count(self):
        for task in self:
            task.returned_count = len(task.sudo().submission_ids.filtered(
                lambda s: s.state == 'returned'))

    @api.depends('state', 'returned_count', 'cancelled_on', 'assignee_id', 'member_ids')
    @api.depends_context('uid')
    def _compute_can_open_dispute(self):
        me = self.env.user.partner_id
        today = fields.Date.context_today(self)
        for task in self:
            mine = me in task._coop_executors()
            task.can_open_dispute = bool(mine and not task.is_recurring and (
                (task.state == 'assigned' and task.returned_count > RETURNS_BEFORE_DISPUTE)
                or (task.state == 'cancelled' and not task.cancel_by_arbiter
                    and task.sudo().submission_ids and task.cancelled_on
                    and (today - task.cancelled_on).days <= CANCEL_DISPUTE_DAYS)))

    @api.depends('coop_specialization_id', 'payer_kind', 'project_id')
    def _compute_median_hint(self):
        Task = self.env['coop.bounty.task'].sudo()
        for task in self:
            task.median_hint = False
            if not task.coop_specialization_id:
                continue
            # Медиана — среди задач того же токена: токены разных проектов
            # не сравнимы друг с другом.
            domain = [('state', '=', 'accepted'), ('id', '!=', task._origin.id or 0),
                      ('coop_specialization_id', '=', task.coop_specialization_id.id),
                      ('reward_tokens', '>', 0)]
            if task.payer_kind == 'platform':
                domain.append(('payer_kind', '=', 'platform'))
            elif task.project_id:
                domain.append(('project_id', '=', task.project_id.id))
            else:
                continue
            rewards = Task.search(domain).mapped('reward_tokens')
            if len(rewards) < MEDIAN_MIN:
                continue
            task.median_hint = _('%(value)s %(unit)s — медиана %(count)s принятых задач этой специализации',
                                 value=_tokens(median(rewards)), unit=task.token_unit,
                                 count=len(rewards))

    @api.depends('payer_id')
    def _compute_payer_answer_label(self):
        for task in self:
            payer = task.payer_id
            if not payer or not payer.coop_bounty_answer_count:
                task.payer_answer_label = False
            elif payer.coop_bounty_answer_days < 1:
                task.payer_answer_label = _('в течение дня')
            else:
                task.payer_answer_label = _('за %s дн. в среднем') % (
                    ('%.1f' % payer.coop_bounty_answer_days).replace('.', ',').replace(',0', ''))

    @api.depends('state', 'submitted_on')
    def _compute_answer_due(self):
        for task in self:
            task.answer_due = (task.submitted_on + timedelta(days=DISPUTE_AFTER_DAYS)
                               if task.state == 'submitted' and task.submitted_on else False)

    def write(self, vals):
        terms = [name for name in P2_TERMS if name in vals]
        if terms:
            locked = self.filtered(lambda t: t.state != 'draft'
                                   and any(t[name] != vals[name] for name in terms))
            if locked:
                raise UserError(_(
                    'Условия оплаты опубликованной задачи не меняют: под них уже подали заявки. '
                    'Верните задачу в черновик.'))
        dissolve = self.browse()
        if 'assignee_id' in vals and not vals['assignee_id']:
            dissolve = self.filtered('member_ids')
        result = super().write(vals)
        # Снят исполнитель — команды больше нет: остальные снова просто
        # подали заявку, и автор соберёт команду заново.
        for task in dissolve.sudo():
            partners = task.member_ids.mapped('partner_id')
            task.application_ids.filtered(
                lambda a: a.state == 'approved' and a.partner_id in partners).write({'state': 'applied'})
            task.member_ids.unlink()
        return result

    # ── Деньги ───────────────────────────────────────────────────────────

    def _coop_planned_total(self):
        """Сколько задача может выплатить всего: у постоянной — за все результаты."""
        self.ensure_one()
        return self.reward_tokens * (self.repeat_limit if self.is_recurring else 1)

    def _coop_executors(self):
        self.ensure_one()
        return self.member_ids.mapped('partner_id') or self.assignee_id

    def _coop_on_payout(self, payout):
        """Зацепка для реестров: coop_tax пишет строку дохода в натуральной форме."""
        return True

    def _coop_pay_base(self):
        """С какой суммы считается выплата: у этапной задачи — сумма этапа."""
        self.ensure_one()
        return self.reward_tokens

    def _coop_pay(self, partial=False, submission=None, amount=None):
        """Провести выплаты: одному, команде по долям или сдавшему результат
        постоянной задачи. Задача платформы — токенами услуг платформы из
        фонда задач, задача проекта — начислением токенов проекта.
        `amount` — сумма явно (приз конкурса), иначе — `_coop_pay_base`."""
        self.ensure_one()
        factor = (self.partial_percent / 100.0) if partial else 1.0
        base = self._coop_pay_base() if amount is None else amount
        total = int(round(base * factor))
        if submission:
            plan = [(submission.partner_id, 1.0)]
        elif self.member_ids:
            shares = self.member_ids.mapped('share_percent')
            if not any(shares):
                plan = [(m.partner_id, 1.0 / len(self.member_ids)) for m in self.member_ids]
            elif abs(sum(shares) - 100.0) > 0.01:
                raise UserError(_('Доли команды в сумме должны давать 100 %%, сейчас %(shares)s %%.',
                                  shares=round(sum(shares), 2)))
            else:
                plan = [(m.partner_id, m.share_percent / 100.0) for m in self.member_ids]
        else:
            plan = [(self.assignee_id, 1.0)]
        Payout = self.env['coop.bounty.payout'].sudo()
        today = fields.Date.context_today(self)
        description = _('Задача «%s»') % self.name
        payouts = Payout.browse()
        left = total
        for number, (partner, share) in enumerate(plan):
            amount = left if number == len(plan) - 1 else int(round(total * share))
            left -= amount
            if amount <= 0:
                continue
            values = {'task_id': self.id, 'partner_id': partner.id, 'amount': amount,
                      'partial': bool(partial), 'date': today,
                      'submission_id': submission.id if submission else False}
            if self.payer_kind == 'platform':
                values['transaction_id'] = self.env['coop.token.transaction'].sudo().create({
                    'partner_id': partner.id, 'amount': amount, 'kind': 'grant',
                    'description': description, 'res_model': self._name, 'res_id': self.id,
                }).id
            elif self.project_id:
                # Токены проекта — учёт в узле (решения 668, 690).
                values['token_move_id'] = self.env['coop.project.token.move'].sudo().create({
                    'project_id': self.project_id.id, 'partner_id': partner.id, 'amount': amount,
                    'task_id': self.id, 'description': description, 'date': today,
                }).id
            payout = Payout.create(values)
            self._coop_on_payout(payout)
            payouts |= payout
        return payouts

    def action_accept_partial(self):
        return self.with_context(coop_bounty_partial=True).action_accept()

    # ── Команда ──────────────────────────────────────────────────────────

    def action_start_team(self):
        """Начать неполной командой: остальные заявки отклоняются."""
        for task in self:
            task.check_access('write')
            if task.state != 'published' or not task.member_ids:
                raise UserError(_('Начать работу командой можно, когда утверждён хотя бы один исполнитель.'))
            task.sudo()._coop_team_ready()
        return True

    def _coop_team_ready(self):
        self.ensure_one()
        self.application_ids.filtered(lambda a: a.state == 'applied').write({'state': 'rejected'})
        self.write({'state': 'assigned', 'assigned_on': fields.Date.context_today(self),
                    'reminded_on': False})
        self.message_post(body=_('Команда собрана: %s. Результат за команду сдаёт %s.') % (
            ', '.join(self.member_ids.mapped('partner_id.display_name')),
            self.assignee_id.display_name))

    # ── Постоянная задача: сдать без заявки ─────────────────────────────

    def _coop_recurring_block(self):
        """Почему текущий человек не может сдать результат — или пусто."""
        self.ensure_one()
        if not self.is_recurring or self.state != 'published':
            return _('Сдать без заявки можно только открытую постоянную задачу.')
        if self.repeat_done >= self.repeat_limit:
            return _('Лимит оплаченных результатов исчерпан.')
        user = self.env.user
        if self.payer_id in user.coop_publisher_partner_ids:
            return _('Это задача вашей организации — результат по ней сдают другие.')
        pending = self.sudo().submission_ids.filtered(
            lambda s: s.partner_id == user.partner_id and s.state == 'review')
        if pending:
            return _('Ваш результат уже на проверке — дождитесь ответа автора.')
        return False

    def action_submit_recurring(self):
        self.ensure_one()
        block = self._coop_recurring_block()
        if block:
            raise UserError(block)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Сдать результат'),
            'res_model': 'coop.bounty.submit',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_task_id': self.id},
        }

    def _coop_do_submit(self, link=False, note=False, attachments=None):
        self.ensure_one()
        if not self.is_recurring:
            return super()._coop_do_submit(link, note, attachments)
        block = self._coop_recurring_block()
        if block:
            raise UserError(block)
        me = self.env.user.partner_id
        Submission = self.env['coop.bounty.submission'].sudo()
        version = Submission.search_count([('task_id', '=', self.id), ('partner_id', '=', me.id)]) + 1
        submission = Submission.create({'task_id': self.id, 'partner_id': me.id,
                                        'version': version, 'link': link, 'note': note})
        if attachments:
            attachments.sudo().write({'res_model': submission._name, 'res_id': submission.id})
            submission.attachment_ids = [(6, 0, attachments.ids)]
        task = self.sudo()
        task.message_post(body=_('Сдан результат: %(who)s, версия %(version)s.',
                                 who=me.display_name, version=version))
        self.env['coop.notification'].sudo()._notify(
            task.manager_id.partner_id,
            _('По постоянной задаче «%s» сдан результат — проверьте его.') % task.name,
            record=task, kind='other')
        return True

    def _coop_close_recurring(self):
        """Лимит исчерпан: задача принята, непроверенные сдачи возвращаются."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        self.submission_ids.filtered(lambda s: s.state == 'review').write({
            'state': 'returned', 'reviewed_on': today,
            'review_note': _('Лимит оплаченных результатов исчерпан — задача закрыта.')})
        self.write({'state': 'accepted', 'accepted_on': today})
        self.message_post(body=_('Оплачено результатов: %s из %s — задача закрыта.') % (
            self.repeat_done, self.repeat_limit))

    def action_apply(self):
        if any(self.mapped('is_recurring')):
            raise UserError(_('У постоянной задачи заявок нет: сдайте результат сразу.'))
        return super().action_apply()

    def action_publish(self):
        result = super().action_publish()
        # Способ у постоянной задачи не выбирают в заявке — он один (решение 690).
        for task in self.filtered('is_recurring'):
            task.payment_mode = task.allowed_method_ids[:1].code or False
        return result

    # ── Спор от исполнителя ──────────────────────────────────────────────

    def action_open_executor_dispute(self):
        self.ensure_one()
        if not self.can_open_dispute:
            raise UserError(_(
                'Открыть спор исполнитель может, если результат вернули на доработку больше '
                'двух раз или задачу со сданным результатом отменили (в течение недели).'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Открыть спор'),
            'res_model': 'coop.bounty.dispute.open',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_task_id': self.id},
        }


class CoopBountyApplicationP2(models.Model):
    _inherit = 'coop.bounty.application'

    def action_approve(self):
        team = self.filtered(lambda a: a.task_id.executor_limit > 1)
        if team:
            team._coop_check_author()
            team.sudo()._coop_approve_to_team()
        rest = self - team
        return super(CoopBountyApplicationP2, rest).action_approve() if rest else True

    def _coop_approve_to_team(self):
        """Утвердить в команду: первый утверждённый сдаёт результат за всех;
        задача открыта для заявок, пока команда не собрана."""
        Member = self.env['coop.bounty.member'].sudo()
        today = fields.Date.context_today(self)
        for record in self:
            task = record.task_id
            if task.state != 'published':
                raise UserError(_('Собрать команду можно только по открытой задаче.'))
            if record.state != 'applied':
                raise UserError(_('Утвердить можно только поданную заявку.'))
            if task.member_count >= task.executor_limit:
                raise UserError(_('Команда уже собрана.'))
            record.state = 'approved'
            Member.create({'task_id': task.id, 'partner_id': record.partner_id.id})
            if not task.assignee_id:
                method = record.method_id or task.allowed_method_ids[:1]
                task.write({'assignee_id': record.partner_id.id, 'payment_mode': method.code or False,
                            'assigned_on': today})
            task.message_post(body=_('В команду утверждён %(who)s — %(count)s из %(limit)s.',
                                     who=record.partner_id.display_name,
                                     count=task.member_count, limit=task.executor_limit))
            if task.member_count >= task.executor_limit:
                task._coop_team_ready()
        return True

    def action_reject(self):
        self._coop_check_author()
        for record in self.sudo():
            task = record.task_id
            if task.assignee_id != record.partner_id:
                task.member_ids.filtered(lambda m: m.partner_id == record.partner_id).unlink()
        return super().action_reject()


class CoopBountyApplyP2(models.TransientModel):
    _inherit = 'coop.bounty.apply'

    def action_confirm(self):
        if self.task_id.is_recurring:
            raise UserError(_('У постоянной задачи заявок нет: сдайте результат сразу.'))
        return super().action_confirm()


class CoopBountyReturnP2(models.TransientModel):
    _inherit = 'coop.bounty.return'

    submission_id = fields.Many2one('coop.bounty.submission', string='Сдача')

    def action_confirm(self):
        self.ensure_one()
        sub = self.submission_id
        if not sub:
            return super().action_confirm()
        task = sub.task_id
        task.check_access('write')
        if sub.state != 'review':
            raise UserError(_('Эта сдача уже проверена.'))
        sub.sudo().write({'state': 'returned', 'review_note': self.note,
                          'reviewed_on': fields.Date.context_today(self)})
        task.sudo().message_post(body=_('Результат %(who)s возвращён: %(note)s',
                                        who=sub.partner_id.display_name, note=self.note))
        self.env['coop.notification'].sudo()._notify(
            sub.partner_id, _('Результат по задаче «%(name)s» возвращён: %(note)s',
                              name=task.name, note=self.note),
            record=task, kind='other')
        return {'type': 'ir.actions.act_window_close'}


class CoopBountyDisputeOpen(models.TransientModel):
    """Исполнитель открывает спор: причина обязательна, разбирает администратор."""
    _name = 'coop.bounty.dispute.open'
    _description = 'Открыть спор'

    task_id = fields.Many2one('coop.bounty.task', string='Задача', required=True)
    reason = fields.Text(string='В чём спор', required=True)

    def action_confirm(self):
        self.ensure_one()
        task = self.task_id
        if not task.can_open_dispute:
            raise UserError(_('Открыть спор по этой задаче сейчас нельзя.'))
        today = fields.Date.context_today(self)
        task = task.sudo()
        task.write({'state': 'dispute', 'dispute_on': today, 'dispute_by': 'executor',
                    'dispute_reason': self.reason, 'dispute_decision': False})
        task.message_post(body=_('Исполнитель открыл спор: %s') % self.reason)
        arbiters = self.env.ref('coop_base.group_coop_platform').sudo().user_ids.mapped('partner_id')
        self.env['coop.notification'].sudo()._notify(
            arbiters | task.manager_id.partner_id,
            _('Открыт спор по задаче «%s» — его разбирает администратор платформы.') % task.name,
            record=task, kind='other')
        return {'type': 'ir.actions.act_window_close'}


class ResPartnerP2(models.Model):
    _inherit = 'res.partner'

    coop_bounty_answer_days = fields.Float(
        string='Отвечает по задачам в среднем, дней', digits=(4, 1),
        compute='_compute_coop_bounty_answer',
        help='Среднее число дней от сдачи результата до ответа автора — принятия или возврата.')
    coop_bounty_answer_count = fields.Integer(compute='_compute_coop_bounty_answer')

    def _compute_coop_bounty_answer(self):
        Submission = self.env['coop.bounty.submission'].sudo()
        for partner in self:
            subs = Submission.search([('task_id.payer_id', '=', partner.id),
                                      ('reviewed_on', '!=', False), ('date', '!=', False)],
                                     limit=200, order='id desc') if partner.id else Submission
            days = [max((s.reviewed_on - s.date).days, 0) for s in subs]
            partner.coop_bounty_answer_count = len(days)
            partner.coop_bounty_answer_days = round(sum(days) / len(days), 1) if days else 0
