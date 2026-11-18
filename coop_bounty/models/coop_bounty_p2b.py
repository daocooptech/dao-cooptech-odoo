# -*- coding: utf-8 -*-
"""Улучшения П2, второй кусок (№ 465; решения 671, 689, 690).

- Конкурс (п. 7): работы присылают без заявки до срока, автор присуждает
  1–3 призовых места; резервируется сумма всех мест; итог узнают все
  участники (баунти Superteam, спринты Zealy). Присланную работу не
  правят: конкурс сравнивает то, что пришло к сроку.
- Этапы (п. 12): у крупной задачи — этапы со своей суммой, сдачей и
  приёмкой; каждый принятый этап оплачивается сразу (безопасная сделка
  Kwork, удержание Replit).
- Резерв задачи проекта (п. 19, решение 689): проект выделяет токены на
  задачи; при публикации сумма задачи блокируется из них и до приёмки или
  отмены на другое не уходит. Как и фонд платформы, блокировка — не
  отдельная запись, а сумма открытых задач проекта: отмена освобождает
  её сама, а расходиться с задачами ей не с чего.
"""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .coop_bounty import RESERVED_STATES
from .coop_bounty_p2 import _tokens

PLACES = [('0', 'Без места'), ('1', '1-е место'), ('2', '2-е место'), ('3', '3-е место')]
# Одна сдача — обычная задача, а не этапы.
MIN_STAGES = 2
MAX_STAGES = 10


class CoopBountyPrize(models.Model):
    """Призовое место конкурса. Победитель записывается при итоге —
    именем, а не ссылкой на работу: работу видят только её автор и
    организатор, а победителя — все."""
    _name = 'coop.bounty.prize'
    _description = 'Призовое место конкурса'
    _order = 'task_id, place'

    task_id = fields.Many2one('coop.bounty.task', string='Конкурс', required=True,
                              ondelete='cascade', index=True)
    place = fields.Integer(string='Место', required=True, default=1)
    amount = fields.Integer(string='Приз, токенов', required=True)
    submission_id = fields.Many2one('coop.bounty.submission', string='Работа', readonly=True,
                                    ondelete='set null')
    winner_id = fields.Many2one('res.partner', string='Победитель', readonly=True)
    token_unit = fields.Char(related='task_id.token_unit', string='Токен')

    _place_unique = models.Constraint('unique(task_id, place)', 'Это место в конкурсе уже есть.')
    _place_range = models.Constraint('check(place >= 1 and place <= 3)',
                                     'Призовых мест — от одного до трёх.')
    _amount_positive = models.Constraint('check(amount > 0)', 'Приз — больше нуля токенов.')

    def _coop_check_draft(self, tasks):
        if tasks.filtered(lambda t: t.state != 'draft'):
            raise UserError(_('Призы опубликованного конкурса не меняют: под них уже присылают работы.'))

    @api.model_create_multi
    def create(self, vals_list):
        prizes = super().create(vals_list)
        self._coop_check_draft(prizes.mapped('task_id'))
        return prizes

    def write(self, vals):
        if set(vals) - {'submission_id', 'winner_id'}:
            self._coop_check_draft(self.mapped('task_id'))
        return super().write(vals)

    def unlink(self):
        self._coop_check_draft(self.mapped('task_id'))
        return super().unlink()


class CoopBountyStage(models.Model):
    """Этап задачи: своя сумма, своя сдача, своя приёмка и выплата."""
    _name = 'coop.bounty.stage'
    _description = 'Этап задачи'
    _order = 'task_id, sequence, id'

    task_id = fields.Many2one('coop.bounty.task', string='Задача', required=True,
                              ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Этап', required=True)
    amount = fields.Integer(string='Сумма этапа', required=True)
    state = fields.Selection([
        ('todo', 'Впереди'),
        ('review', 'На проверке'),
        ('accepted', 'Принят'),
    ], string='Состояние', default='todo', required=True, readonly=True)
    accepted_on = fields.Date(string='Принят', readonly=True)
    payout_ids = fields.One2many('coop.bounty.payout', 'stage_id', string='Выплаты')
    paid_amount = fields.Integer(string='Выплачено', compute='_compute_paid_amount')
    is_current = fields.Boolean(string='Текущий', compute='_compute_is_current')
    token_unit = fields.Char(related='task_id.token_unit', string='Токен')

    _amount_positive = models.Constraint('check(amount > 0)', 'Сумма этапа — больше нуля токенов.')

    def _compute_paid_amount(self):
        for stage in self:
            stage.paid_amount = sum(stage.sudo().payout_ids.mapped('amount'))

    @api.depends('task_id.stage_current_id')
    def _compute_is_current(self):
        for stage in self:
            stage.is_current = stage == stage.task_id.stage_current_id

    def _coop_check_draft(self, tasks):
        if tasks.filtered(lambda t: t.state != 'draft'):
            raise UserError(_('Этапы опубликованной задачи не меняют: под них уже подали заявки. '
                              'Верните задачу в черновик.'))

    @api.model_create_multi
    def create(self, vals_list):
        stages = super().create(vals_list)
        self._coop_check_draft(stages.mapped('task_id'))
        return stages

    def write(self, vals):
        if set(vals) - {'state', 'accepted_on'}:
            self._coop_check_draft(self.mapped('task_id'))
        return super().write(vals)

    def unlink(self):
        self._coop_check_draft(self.mapped('task_id'))
        return super().unlink()


class CoopBountyPayoutP2b(models.Model):
    _inherit = 'coop.bounty.payout'

    stage_id = fields.Many2one('coop.bounty.stage', string='Этап', ondelete='set null', index=True)
    prize_place = fields.Integer(string='Место в конкурсе')


class CoopBountySubmissionP2b(models.Model):
    _inherit = 'coop.bounty.submission'

    state = fields.Selection(selection_add=[('not_won', 'Без призового места')],
                             ondelete={'not_won': 'set default'})
    place = fields.Integer(string='Место', readonly=True)
    stage_id = fields.Many2one('coop.bounty.stage', string='Этап', ondelete='set null')


class CoopBountyTaskP2b(models.Model):
    _inherit = 'coop.bounty.task'

    # п. 7 — конкурс
    is_contest = fields.Boolean(
        string='Конкурс', tracking=True,
        help='Работы присылают без заявки до срока, автор присуждает 1–3 призовых места. '
             'Резервируется сумма всех мест; итог узнают все участники.')
    prize_ids = fields.One2many('coop.bounty.prize', 'task_id', string='Призовые места')
    contest_entry_count = fields.Integer(string='Работ прислано', compute='_compute_contest_info')
    can_submit_contest = fields.Boolean(compute='_compute_contest_info')
    can_sum_up = fields.Boolean(compute='_compute_contest_info')

    # п. 12 — этапы
    stage_ids = fields.One2many('coop.bounty.stage', 'task_id', string='Этапы')
    stage_count = fields.Integer(string='Этапов', compute='_compute_stage_info')
    stage_done_count = fields.Integer(string='Принято этапов', compute='_compute_stage_info')
    stage_current_id = fields.Many2one('coop.bounty.stage', string='Текущий этап',
                                       compute='_compute_stage_info')
    stage_label = fields.Char(string='Этап', compute='_compute_stage_info')

    # п. 19 — резерв: где лежит сумма задачи до приёмки
    reserve_label = fields.Char(string='Резерв', compute='_compute_reserve_label')

    @api.constrains('is_contest', 'is_recurring', 'executor_limit', 'partial_percent', 'stage_ids')
    def _check_p2b_kind(self):
        for task in self:
            if task.is_contest:
                if task.is_recurring:
                    raise ValidationError(_('Конкурс не бывает постоянной задачей: призы — один раз.'))
                if task.executor_limit > 1:
                    raise ValidationError(_('В конкурсе каждый участвует сам — команды нет.'))
                if task.partial_percent:
                    raise ValidationError(_('У конкурса частичной оплаты нет: платят призовые места.'))
            if task.stage_ids and (task.is_contest or task.is_recurring):
                raise ValidationError(_('Этапы — у задачи с исполнителем, не у конкурса и не у постоянной.'))
            if len(task.stage_ids) > MAX_STAGES:
                raise ValidationError(_('Этапов — не больше десяти.'))

    @api.depends('is_contest', 'state', 'deadline', 'submission_ids', 'payer_id')
    @api.depends_context('uid')
    def _compute_contest_info(self):
        today = fields.Date.context_today(self)
        arbiter = self._coop_is_arbiter()
        for task in self:
            subs = task.sudo().submission_ids if task.is_contest else self.env['coop.bounty.submission']
            task.contest_entry_count = len(subs)
            task.can_submit_contest = bool(task.id and task.is_contest and not task._coop_contest_block())
            waiting = subs.filtered(lambda s: s.state == 'review')
            over = task.state in ('submitted', 'dispute') or (
                task.state == 'published' and task.deadline and task.deadline < today)
            task.can_sum_up = bool(task.is_contest and waiting and over and (
                task.coop_can_edit or (arbiter and task.state == 'dispute')))

    @api.depends('stage_ids', 'stage_ids.state', 'stage_ids.sequence', 'stage_ids.amount')
    def _compute_stage_info(self):
        for task in self:
            stages = task.stage_ids.sorted(lambda s: (s.sequence, s.id))
            open_stages = stages.filtered(lambda s: s.state != 'accepted')
            current = open_stages[:1]
            task.stage_count = len(stages)
            task.stage_done_count = len(stages) - len(open_stages)
            task.stage_current_id = current
            task.stage_label = _('Этап %(number)s из %(count)s: %(name)s — %(amount)s %(unit)s',
                                 number=len(stages) - len(open_stages) + 1, count=len(stages),
                                 name=current.name, amount=_tokens(current.amount),
                                 unit=task.sudo().token_unit) if current else False

    @api.depends('state', 'payer_kind', 'paid_amount', 'reward_tokens', 'project_id')
    def _compute_reserve_label(self):
        for task in self:
            if task.state not in RESERVED_STATES:
                task.reserve_label = False
                continue
            left = _tokens(max(task._coop_planned_total() - task.paid_amount, 0))
            # Подпись токена — из проекта: исполнитель его карточку может и не видеть.
            unit = task.sudo().token_unit
            if task.payer_kind == 'platform':
                task.reserve_label = _('%(amount)s %(unit)s отложено в фонде задач платформы до приёмки',
                                       amount=left, unit=unit)
            else:
                task.reserve_label = _('%(amount)s %(unit)s заблокировано у проекта до приёмки',
                                       amount=left, unit=unit)

    @api.onchange('is_contest', 'prize_ids', 'stage_ids')
    def _onchange_p2b_total(self):
        # Сумма задачи — сумма призов или этапов: одно число, а не два.
        if self.is_contest and self.prize_ids:
            self.reward_tokens = sum(self.prize_ids.mapped('amount'))
        elif self.stage_ids:
            self.reward_tokens = sum(self.stage_ids.mapped('amount'))

    def write(self, vals):
        if 'is_contest' in vals and self.filtered(
                lambda t: t.state != 'draft' and t.is_contest != vals['is_contest']):
            raise UserError(_('Вид опубликованной задачи не меняют. Верните задачу в черновик.'))
        return super().write(vals)

    # ── Деньги ───────────────────────────────────────────────────────────

    def _coop_planned_total(self):
        self.ensure_one()
        if self.is_contest:
            return sum(self.prize_ids.mapped('amount'))
        return super()._coop_planned_total()

    def _coop_pay_base(self):
        self.ensure_one()
        if self.stage_current_id:
            return self.stage_current_id.amount
        return super()._coop_pay_base()

    def _coop_pay(self, partial=False, submission=None, amount=None):
        stage = self.stage_current_id if not self.is_contest else False
        payouts = super()._coop_pay(partial=partial, submission=submission, amount=amount)
        if stage:
            payouts.write({'stage_id': stage.id})
        return payouts

    def _coop_check_publishable(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.is_contest:
            prizes = self.prize_ids.sorted('place')
            if not prizes:
                raise UserError(_('Задайте призовые места: от одного до трёх, у каждого — сумма.'))
            if prizes.mapped('place') != list(range(1, len(prizes) + 1)):
                raise UserError(_('Места идут подряд с первого: 1, 2, 3.'))
            amounts = prizes.mapped('amount')
            if amounts != sorted(amounts, reverse=True):
                raise UserError(_('Приз за место ниже не больше приза за место выше.'))
            if not self.deadline or self.deadline <= today:
                raise UserError(_('Укажите срок приёма работ — позже сегодняшнего дня.'))
            self.reward_tokens = sum(amounts)
        if self.stage_ids:
            if len(self.stage_ids) < MIN_STAGES:
                raise UserError(_('Этапов — хотя бы два: одна сдача — это обычная задача.'))
            self.reward_tokens = sum(self.stage_ids.mapped('amount'))
        result = super()._coop_check_publishable()
        if self.payer_kind == 'project':
            self._coop_reserve_project()
        return result

    def _coop_reserve_project(self):
        """Заблокировать сумму задачи у проекта (решение 689)."""
        self.ensure_one()
        project = self.project_id.sudo()
        # Свежий остаток: в одной транзакции публикуют и по нескольку задач.
        project.invalidate_recordset(['coop_bounty_blocked', 'coop_bounty_paid', 'coop_bounty_free'])
        unit = project._coop_token_unit()
        if not project.coop_bounty_token_limit:
            raise UserError(_(
                'Проект «%(name)s» не выделил токенов на задачи: сумма задачи блокируется из них '
                'при публикации. Укажите «Токенов на задачи» во вкладке «Токен проекта».',
                name=project.name))
        need = self._coop_planned_total() - self.paid_amount
        if project.coop_bounty_free < need:
            raise UserError(_(
                'Не хватает токенов проекта на задачи: нужно %(need)s %(unit)s, свободно %(free)s. '
                'Уменьшите сумму или выделите проекту больше токенов на задачи.',
                need=_tokens(need), unit=unit, free=_tokens(project.coop_bounty_free)))

    def action_publish(self):
        result = super().action_publish()
        # Способ у конкурса не выбирают в заявке — он один (решение 690).
        for task in self.filtered('is_contest'):
            task.payment_mode = task.allowed_method_ids[:1].code or False
        return result

    def action_reset_to_draft(self):
        if self.filtered('paid_amount'):
            raise UserError(_('По задаче уже есть выплаты — в черновик её не вернуть: условия, '
                              'по которым платили, должны остаться прежними.'))
        return super().action_reset_to_draft()

    # ── Приёмка: этапы ───────────────────────────────────────────────────

    def action_accept(self):
        if self.filtered('is_contest'):
            raise UserError(_('Итог конкурса подводят окном «Подвести итог»: места и призы.'))
        staged = self.filtered('stage_ids')
        for task in staged:
            stage = task.stage_current_id
            if not stage:
                raise UserError(_('Все этапы уже приняты.'))
            last = stage == task.stage_ids.sorted(lambda s: (s.sequence, s.id))[-1]
            if last:
                super(CoopBountyTaskP2b, task).action_accept()
                stage.sudo().write({'state': 'accepted',
                                    'accepted_on': fields.Date.context_today(task)})
            else:
                task._coop_accept_stage(stage)
        rest = self - staged
        return super(CoopBountyTaskP2b, rest).action_accept() if rest else True

    def _coop_accept_stage(self, stage):
        """Принять промежуточный этап: выплата сразу, задача — снова в работе."""
        self.ensure_one()
        partial = bool(self.env.context.get('coop_bounty_partial'))
        if self.state not in ('submitted', 'dispute'):
            raise UserError(_('Принять можно только сданный этап.'))
        if not self.assignee_id:
            raise UserError(_('У задачи нет исполнителя.'))
        if partial and not self.partial_percent:
            raise UserError(_('Частичной оплаты у задачи нет: её задают до публикации.'))
        today = fields.Date.context_today(self)
        payouts = self._coop_pay(partial=partial)
        paid = sum(payouts.mapped('amount'))
        stage.sudo().write({'state': 'accepted', 'accepted_on': today})
        self.submission_ids.sudo().filtered(lambda s: s.state == 'review').write({
            'state': 'accepted', 'reviewed_on': today})
        self.write({'state': 'assigned', 'submitted_on': False, 'reminded_on': False,
                    'paid_amount': self.paid_amount + paid})
        following = self.stage_current_id
        body = _('Этап «%(stage)s» принят, начислено %(amount)s %(unit)s. Дальше — этап «%(next)s».',
                 stage=stage.name, amount=_tokens(paid), unit=self.token_unit, next=following.name)
        if partial:
            body = _('Этап «%(stage)s» принят частично (%(percent)s %%), начислено %(amount)s %(unit)s. '
                     'Дальше — этап «%(next)s».', stage=stage.name, percent=self.partial_percent,
                     amount=_tokens(paid), unit=self.token_unit, next=following.name)
        self.message_post(body=body)
        self.env['coop.notification'].sudo()._notify(
            self._coop_executors(),
            _('Этап «%(stage)s» по задаче «%(name)s» принят, начислено %(amount)s %(unit)s.',
              stage=stage.name, name=self.name, amount=_tokens(paid), unit=self.token_unit),
            record=self, kind='other')
        return payouts

    def _coop_do_submit(self, link=False, note=False, attachments=None):
        self.ensure_one()
        if self.is_contest:
            return self._coop_submit_contest(link, note, attachments)
        stage = self.stage_current_id
        result = super()._coop_do_submit(link, note, attachments)
        if stage:
            submission = self.sudo().submission_ids.sorted('id')[-1:]
            submission.stage_id = stage
            stage.sudo().state = 'review'
            self.sudo().message_post(body=_('Сдан этап «%s».') % stage.name)
        return result

    def _coop_do_return(self, note):
        result = super()._coop_do_return(note)
        self.sudo().stage_ids.filtered(lambda s: s.state == 'review').write({'state': 'todo'})
        return result

    # ── Конкурс ──────────────────────────────────────────────────────────

    def _coop_contest_block(self):
        """Почему текущий человек не может прислать работу — или пусто."""
        self.ensure_one()
        if not self.is_contest or self.state != 'published':
            return _('Работы принимаются только по открытому конкурсу.')
        if self.deadline and self.deadline < fields.Date.context_today(self):
            return _('Приём работ закончился %s.') % self.deadline.strftime('%d.%m.%Y')
        user = self.env.user
        if self.payer_id in user.coop_publisher_partner_ids:
            return _('Это конкурс вашей организации — работы присылают другие.')
        if self.sudo().submission_ids.filtered(lambda s: s.partner_id == user.partner_id):
            return _('Ваша работа уже на конкурсе. Присланную не меняют: сравнивают то, что пришло к сроку.')
        return False

    def action_submit_contest(self):
        self.ensure_one()
        block = self._coop_contest_block()
        if block:
            raise UserError(block)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Прислать работу на конкурс'),
            'res_model': 'coop.bounty.submit',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_task_id': self.id},
        }

    def _coop_submit_contest(self, link, note, attachments):
        block = self._coop_contest_block()
        if block:
            raise UserError(block)
        me = self.env.user.partner_id
        submission = self.env['coop.bounty.submission'].sudo().create({
            'task_id': self.id, 'partner_id': me.id, 'version': 1, 'link': link, 'note': note})
        if attachments:
            attachments.sudo().write({'res_model': submission._name, 'res_id': submission.id})
            submission.attachment_ids = [(6, 0, attachments.ids)]
        # Без имени: до итога участники не знают, кто ещё прислал.
        self.sudo().message_post(body=_('На конкурс прислана работа — всего %s.')
                                 % len(self.sudo().submission_ids))
        return True

    def action_apply(self):
        if self.filtered('is_contest'):
            raise UserError(_('В конкурсе заявок нет: пришлите работу до срока.'))
        return super().action_apply()

    def action_return_for_revision(self):
        if self.filtered('is_contest'):
            raise UserError(_('Работы конкурса на доработку не возвращают: итог — по присланному к сроку.'))
        return super().action_return_for_revision()

    def action_open_contest_result(self):
        self.ensure_one()
        if not self.can_sum_up:
            raise UserError(_('Итог подводят после срока приёма работ, когда есть хотя бы одна работа.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Итог конкурса'),
            'res_model': 'coop.bounty.contest.result',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_task_id': self.id},
        }

    def _coop_contest_finish(self, places, decision=False):
        """Присудить места: {работа: место}. Не присуждённые места не
        платятся — их приз остаётся в фонде или у проекта."""
        self.ensure_one()
        task = self.sudo()
        prizes = {prize.place: prize for prize in task.prize_ids}
        used = sorted(places.values())
        if not used:
            raise UserError(_('Выберите хотя бы одну работу-победителя.'))
        if len(set(used)) != len(used):
            raise UserError(_('Одно место — одна работа.'))
        if any(place not in prizes for place in used):
            raise UserError(_('Такого места в конкурсе нет.'))
        if used != list(range(1, len(used) + 1)):
            raise UserError(_('Места присуждают подряд с первого: без первого нет второго.'))
        if any(sub.task_id != task or sub.state != 'review' for sub in places):
            raise UserError(_('Победителем может быть только работа этого конкурса, ещё без итога.'))
        today = fields.Date.context_today(task)
        paid = 0
        winners = []
        for sub, place in sorted(places.items(), key=lambda item: item[1]):
            prize = prizes[place]
            payouts = task._coop_pay(submission=sub, amount=prize.amount)
            payouts.write({'prize_place': place})
            paid += sum(payouts.mapped('amount'))
            prize.write({'submission_id': sub.id, 'winner_id': sub.partner_id.id})
            sub.write({'state': 'accepted', 'reviewed_on': today, 'place': place})
            winners.append((place, sub.partner_id, prize.amount))
        others = task.submission_ids.filtered(lambda s: s.state == 'review')
        others.write({'state': 'not_won', 'reviewed_on': today})
        values = {'state': 'accepted', 'accepted_on': today, 'paid_amount': task.paid_amount + paid,
                  'assignee_id': winners[0][1].id}
        if decision:
            values['dispute_decision'] = decision
        task.write(values)
        summary = '; '.join(_('%(place)s-е место — %(who)s, %(amount)s %(unit)s',
                              place=place, who=partner.display_name, amount=_tokens(amount),
                              unit=task.token_unit) for place, partner, amount in winners)
        body = _('Итог конкурса: %(summary)s. Работ прислано: %(count)s.',
                 summary=summary, count=len(task.submission_ids))
        unused = [p for p in prizes if p not in used]
        if unused:
            body += ' ' + _('Не присуждено мест: %s — их призы не выплачены.') % len(unused)
        task.message_post(body=body)
        Notification = self.env['coop.notification'].sudo()
        for place, partner, amount in winners:
            Notification._notify(partner, _(
                'Ваша работа на конкурсе «%(name)s» заняла %(place)s-е место, начислено '
                '%(amount)s %(unit)s.', name=task.name, place=place, amount=_tokens(amount),
                unit=task.token_unit), record=task, kind='other')
        for partner in others.mapped('partner_id'):
            Notification._notify(partner, _(
                'Итог конкурса «%(name)s»: %(summary)s. Ваша работа без призового места — '
                'спасибо за участие.', name=task.name, summary=summary), record=task, kind='other')
        (task.payout_ids.mapped('partner_id') | task.payer_id)._coop_recompute_deal_stats()
        return True

    @api.model
    def _cron_contest_deadline(self):
        """Срок приёма работ прошёл: работы есть — ждём итога автора (через
        семь дней молчания — спор, как у обычной сдачи); работ нет —
        конкурс закрыт, резерв освобождён."""
        today = fields.Date.context_today(self)
        tasks = self.sudo().search([('is_contest', '=', True), ('state', '=', 'published'),
                                    ('deadline', '<', today)])
        Notification = self.env['coop.notification'].sudo()
        for task in tasks:
            count = len(task.submission_ids)
            if count:
                task.write({'state': 'submitted', 'submitted_on': task.deadline + timedelta(days=1)})
                task.message_post(body=_(
                    'Приём работ закончился, прислано %s. Автор подводит итог — через семь дней '
                    'молчания откроется спор.') % count)
                Notification._notify(task.manager_id.partner_id, _(
                    'Приём работ на конкурс «%s» закончился — подведите итог.') % task.name,
                    record=task, kind='other')
            else:
                task.write({'state': 'cancelled', 'cancelled_on': today})
                task.message_post(body=_('Срок прошёл, работ не прислали — конкурс закрыт, резерв освобождён.'))
        return len(tasks)


class CoopBountyApplyP2b(models.TransientModel):
    _inherit = 'coop.bounty.apply'

    def action_confirm(self):
        if self.task_id.is_contest:
            raise UserError(_('В конкурсе заявок нет: пришлите работу до срока.'))
        return super().action_confirm()


class CoopBountySubmitP2b(models.TransientModel):
    _inherit = 'coop.bounty.submit'

    is_contest = fields.Boolean(related='task_id.is_contest')


class CoopBountyDisputeP2b(models.TransientModel):
    _inherit = 'coop.bounty.dispute'

    is_contest = fields.Boolean(related='task_id.is_contest')

    def action_confirm(self):
        self.ensure_one()
        if self.task_id.is_contest and self.outcome != 'cancel':
            raise UserError(_('Спор по конкурсу решают итогом: «Подвести итог» — места и призы. '
                              'Здесь — только отмена конкурса.'))
        return super().action_confirm()


class CoopBountyContestResult(models.TransientModel):
    """Итог конкурса: автор (или администратор в споре) присуждает места."""
    _name = 'coop.bounty.contest.result'
    _description = 'Итог конкурса'

    task_id = fields.Many2one('coop.bounty.task', string='Конкурс', required=True)
    prize_ids = fields.One2many(related='task_id.prize_ids', readonly=True)
    line_ids = fields.One2many('coop.bounty.contest.line', 'wizard_id', string='Работы')
    in_dispute = fields.Boolean(compute='_compute_in_dispute')
    decision = fields.Text(string='Объяснение итога',
                           help='В споре итог подводит администратор платформы — с объяснением.')

    @api.depends('task_id.state')
    def _compute_in_dispute(self):
        for wizard in self:
            wizard.in_dispute = wizard.task_id.state == 'dispute'

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        task = self.env['coop.bounty.task'].browse(
            values.get('task_id') or self.env.context.get('default_task_id'))
        if task and 'line_ids' in fields_list:
            subs = task.sudo().submission_ids.filtered(lambda s: s.state == 'review').sorted('id')
            values['line_ids'] = [(0, 0, {'submission_id': sub.id, 'place': '0'}) for sub in subs]
        return values

    def action_confirm(self):
        self.ensure_one()
        task = self.task_id
        if not task.can_sum_up:
            raise UserError(_('Итог подводят после срока приёма работ, когда есть хотя бы одна работа.'))
        if task.state == 'dispute' and not (self.decision or '').strip():
            raise UserError(_('В споре итог подводят с объяснением — его увидят все участники.'))
        places = {line.submission_id.sudo(): int(line.place)
                  for line in self.line_ids if line.place != '0'}
        task._coop_contest_finish(places, decision=self.decision if task.state == 'dispute' else False)
        return {'type': 'ir.actions.act_window_close'}


class CoopBountyContestLine(models.TransientModel):
    _name = 'coop.bounty.contest.line'
    _description = 'Работа в итоге конкурса'

    wizard_id = fields.Many2one('coop.bounty.contest.result', required=True, ondelete='cascade')
    # Не readonly: поле только для чтения окно не отправляет, и строка
    # приходила на сервер без работы.
    submission_id = fields.Many2one('coop.bounty.submission', string='Работа')
    partner_id = fields.Many2one(related='submission_id.partner_id', string='Участник')
    link = fields.Char(related='submission_id.link', string='Ссылка')
    note = fields.Text(related='submission_id.note', string='Что сделано')
    date = fields.Date(related='submission_id.date', string='Прислано')
    place = fields.Selection(PLACES, string='Место', required=True, default='0')


class CoopProjectReserve(models.Model):
    """Токены проекта на задачи (решение 689): из них блокируется сумма
    каждой опубликованной задачи проекта."""
    _inherit = 'coop.project'

    coop_bounty_token_limit = fields.Integer(
        string='Токенов на задачи',
        help='Сколько своих токенов проект выделяет на задачи краудсорсинга. Сумма задачи '
             'блокируется из них при публикации и до приёмки или отмены на другое не уходит.')
    coop_bounty_blocked = fields.Integer(string='Заблокировано под задачи',
                                         compute='_compute_coop_bounty_reserve')
    coop_bounty_paid = fields.Integer(string='Выплачено за задачи',
                                      compute='_compute_coop_bounty_reserve')
    coop_bounty_free = fields.Integer(string='Свободно для задач',
                                      compute='_compute_coop_bounty_reserve')

    @api.constrains('coop_bounty_token_limit')
    def _check_coop_bounty_token_limit(self):
        for project in self:
            if project.coop_bounty_token_limit < 0:
                raise ValidationError(_('Токенов на задачи — не меньше нуля.'))
            if project.coop_bounty_token_limit and project.coop_bounty_free < 0:
                raise ValidationError(_(
                    'Под задачи проекта уже заблокировано и выплачено %(used)s — выделить меньше нельзя.',
                    used=_tokens(project.coop_bounty_blocked + project.coop_bounty_paid)))

    def _coop_bounty_tasks(self):
        self.ensure_one()
        Task = self.env['coop.bounty.task'].sudo()
        if not self.id:
            return Task
        return Task.search([('project_id', '=', self.id), ('payer_kind', '=', 'project')])

    @api.depends('coop_bounty_token_limit', 'coop_bounty_task_ids.state',
                 'coop_bounty_task_ids.paid_amount', 'coop_bounty_task_ids.reward_tokens')
    def _compute_coop_bounty_reserve(self):
        for project in self:
            tasks = project._coop_bounty_tasks()
            blocked = sum(max(t._coop_planned_total() - t.paid_amount, 0)
                          for t in tasks if t.state in RESERVED_STATES)
            paid = sum(tasks.mapped('paid_amount'))
            project.coop_bounty_blocked = blocked
            project.coop_bounty_paid = paid
            project.coop_bounty_free = (project.coop_bounty_token_limit - blocked - paid
                                        if project.coop_bounty_token_limit else 0)

    def _coop_bounty_fit_limit(self, minimum=0, step=1000):
        """Выделить токены на задачи тем проектам, у кого задачи уже есть,
        а выделенного не хватает: с запасом в четверть, круглым числом.
        Для переноса и демо — задачи, опубликованные до решения 689."""
        fitted = 0
        for project in self.sudo():
            used = project.coop_bounty_blocked + project.coop_bounty_paid
            if not used and not minimum:
                continue
            need = max(int(used * 1.25), minimum)
            need = -(-need // step) * step
            if project.coop_bounty_token_limit < used or not project.coop_bounty_token_limit:
                project.coop_bounty_token_limit = max(need, project.coop_bounty_token_limit)
                fitted += 1
        return fitted
