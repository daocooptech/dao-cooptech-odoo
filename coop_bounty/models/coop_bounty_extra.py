# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .coop_bounty import PAYMENT_METHODS, RESERVED_STATES


class CoopBountyMethod(models.Model):
    """Способ оплаты задачи — справочник из пяти записей.

    Записью, а не набором галочек у задачи: автор отмечает несколько
    способов, исполнитель выбирает один из отмеченных, и выбор из списка
    с отбором по задаче без справочника не построить.
    """
    _name = 'coop.bounty.method'
    _description = 'Способ оплаты задачи'
    _order = 'sequence, id'

    name = fields.Char(string='Способ', required=True)
    code = fields.Selection(PAYMENT_METHODS, string='Код', required=True)
    scope = fields.Selection([
        ('platform', 'Задачи платформы'),
        ('project', 'Задачи проектов'),
        ('both', 'Все задачи'),
    ], string='Для каких задач', required=True)
    note = fields.Char(string='Пояснение')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint('unique(code)', 'Способ с таким кодом уже есть.')


class CoopBountyFund(models.Model):
    """Фонд задач платформы (решение 671 п. 3): 100 тыс. токенов на 3 месяца.

    Резерв не отдельная запись, а сумма открытых задач фонда: задача
    публикуется, только если свободного хватает на всю её сумму, а отмена
    возвращает резерв сама собой — задача просто выпадает из суммы.
    """
    _name = 'coop.bounty.fund'
    _description = 'Фонд задач платформы'
    _order = 'date_start desc, id desc'

    name = fields.Char(string='Фонд', required=True)
    amount = fields.Integer(string='Всего, токенов', required=True, default=100000)
    date_start = fields.Date(string='С', required=True)
    date_end = fields.Date(string='По', required=True)
    task_ids = fields.One2many('coop.bounty.task', 'fund_id', string='Задачи')
    reserved = fields.Integer(string='В резерве', compute='_compute_totals')
    paid = fields.Integer(string='Выплачено', compute='_compute_totals')
    free = fields.Integer(string='Свободно', compute='_compute_totals')
    task_count = fields.Integer(string='Задач', compute='_compute_totals')

    @api.depends('amount', 'task_ids.state', 'task_ids.reward_tokens', 'task_ids.paid_amount',
                 'task_ids.is_recurring', 'task_ids.repeat_limit')
    def _compute_totals(self):
        # Под sudo: свободный остаток фонда видит каждый автор задачи
        # платформы, а задачи фонда в черновиках и отменённые — не каждый.
        # Выплачено — по выплатам (№ 465): частичная приёмка платит меньше
        # суммы, постоянная задача платит по каждому результату, а
        # отменённая постоянная — за то, что успели принять.
        Task = self.env['coop.bounty.task'].sudo()
        for fund in self:
            tasks = Task.search([('fund_id', '=', fund.id)]) if fund.id else Task
            reserved = sum(max(t._coop_planned_total() - t.paid_amount, 0)
                           for t in tasks if t.state in RESERVED_STATES)
            paid = sum(tasks.mapped('paid_amount'))
            fund.reserved = reserved
            fund.paid = paid
            fund.free = fund.amount - reserved - paid
            fund.task_count = len(tasks)

    @api.model
    def _coop_current(self):
        today = fields.Date.context_today(self)
        return self.search([('date_start', '<=', today), ('date_end', '>=', today)], limit=1)


class CoopBountyApply(models.TransientModel):
    """Окно заявки: исполнитель выбирает один из допустимых способов."""
    _name = 'coop.bounty.apply'
    _description = 'Заявка на задачу'

    task_id = fields.Many2one('coop.bounty.task', string='Задача', required=True)
    allowed_method_ids = fields.Many2many(related='task_id.allowed_method_ids')
    method_id = fields.Many2one(
        'coop.bounty.method', string='Способ оплаты', required=True,
        domain="[('id', 'in', allowed_method_ids)]")
    method_code = fields.Selection(related='method_id.code')
    share_percent = fields.Float(related='task_id.share_percent')
    reward_tokens = fields.Integer(related='task_id.reward_tokens')
    message = fields.Text(string='Сообщение автору')
    proposed_deadline = fields.Date(string='Сдам до')
    answer_line_ids = fields.One2many('coop.bounty.apply.answer', 'wizard_id',
                                      string='Вопросы автора')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        task = self.env['coop.bounty.task'].browse(values.get('task_id'))
        if task and 'answer_line_ids' in fields_list:
            values['answer_line_ids'] = [(0, 0, {'question_id': q.id}) for q in task.question_ids]
        return values

    def action_confirm(self):
        self.ensure_one()
        task = self.task_id
        if task.state != 'published':
            raise UserError(_('Заявки принимаются только по опубликованным задачам.'))
        if self.method_id not in task.allowed_method_ids:
            raise UserError(_('Этот способ автор задачи не предлагал.'))
        me = self.env.user.partner_id
        if task.application_ids.filtered(lambda a: a.partner_id == me):
            raise UserError(_('Вы уже подали заявку по этой задаче.'))
        missing = self.answer_line_ids.filtered(
            lambda l: l.question_id.required and not (l.answer or '').strip())
        if missing:
            raise UserError(_('Ответьте на вопросы автора: %s') % '; '.join(missing.mapped('question')))
        if self.proposed_deadline and self.proposed_deadline < fields.Date.context_today(self):
            raise UserError(_('Срок сдачи не может быть в прошлом.'))
        self.env['coop.bounty.application'].sudo().create({
            'task_id': task.id,
            'partner_id': me.id,
            'method_id': self.method_id.id,
            'message': self.message,
            'proposed_deadline': self.proposed_deadline,
            'answer_ids': [(0, 0, {'question_id': l.question_id.id,
                                   'question': l.question_id.name,
                                   'answer': l.answer})
                           for l in self.answer_line_ids if l.question_id],
        })
        task.sudo().message_post(body=_(
            'Подана заявка: %(who)s, способ — %(method)s.',
            who=me.display_name, method=self.method_id.name))
        return {'type': 'ir.actions.act_window_close'}


class CoopBountyDispute(models.TransientModel):
    """Решение администратора платформы по спору (решение 194).

    Решение без объяснения не принимается: спор, закрытый молча, ничем не
    отличается от замолчанного.
    """
    _name = 'coop.bounty.dispute'
    _description = 'Решение по спору'

    task_id = fields.Many2one('coop.bounty.task', string='Задача', required=True)
    criterion_ids = fields.One2many(related='task_id.criterion_ids', readonly=True)
    submission_ids = fields.One2many(related='task_id.submission_ids', readonly=True)
    outcome = fields.Selection([
        ('assignee', 'Засчитать в пользу исполнителя'),
        ('partial', 'Засчитать частично'),
        ('revision', 'Вернуть на доработку'),
        ('cancel', 'Отменить задачу'),
    ], string='Решение', required=True, default='assignee')
    decision = fields.Text(string='Объяснение решения', required=True)
    partial_percent = fields.Integer(related='task_id.partial_percent')
    dispute_by = fields.Selection(related='task_id.dispute_by')
    dispute_reason = fields.Text(related='task_id.dispute_reason')

    def action_confirm(self):
        self.ensure_one()
        task = self.task_id.sudo()
        if not self.env['coop.bounty.task']._coop_is_arbiter():
            raise UserError(_('Спор разбирает администратор платформы.'))
        if task.state != 'dispute':
            raise UserError(_('По этой задаче спора нет.'))
        if self.outcome == 'partial' and not task.partial_percent:
            raise UserError(_('Частичной оплаты у задачи нет: засчитать можно полностью, '
                              'вернуть на доработку или отменить.'))
        task.write({'dispute_decision': self.decision})
        task.message_post(body=_('Решение по спору — %(outcome)s: %(text)s',
                                 outcome=dict(self._fields['outcome'].selection)[self.outcome],
                                 text=self.decision))
        if self.outcome == 'assignee':
            task.with_context(coop_bounty_force_accept=True).action_accept()
        elif self.outcome == 'partial':
            task.with_context(coop_bounty_force_accept=True, coop_bounty_partial=True).action_accept()
        elif self.outcome == 'revision':
            task._coop_do_return(self.decision)
        else:
            task.with_context(coop_bounty_arbiter=True).action_cancel()
        return {'type': 'ir.actions.act_window_close'}


class ResPartner(models.Model):
    """Настройки организации для задач за долю (решения 672, 673)."""
    _inherit = 'res.partner'

    coop_labor_share_cap = fields.Float(
        string='Потолок доли за труд, %', digits=(5, 2),
        help='Наибольшая доля в процентах, которую организация отдаёт за '
             'одну задачу. Пусто — потолка нет.')
    coop_labor_share_form = fields.Selection([
        ('token_share', 'Токен-доля'),
        ('certificate', 'Сертификат на долю'),
        ('contribution', 'Оценка вклада и выделение доли'),
    ], string='Форма доли',
        help='Как организация оформляет долю за задачу. Зависит от закона '
             'страны организации.')
