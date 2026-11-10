# -*- coding: utf-8 -*-
"""Объявление прибыли проекта и её распределение по долям.

Решение владельца 633 (28.10.2026): в коммерческом проекте и в ДАО
доля даёт часть результата и часть прибыли пропорционально долям.
Некоммерческий проект долей не имеет, у кооперативного пай даёт
результат, а не прибыль — поэтому объявить прибыль можно только в
проекте вида «коммерческий» или «ДАО».

Объявление — это решение инициатора: «за такой период проект получил
столько, делим». Само по себе оно денег не двигает. Строки — это
расчёт: кому какая часть. Выплата в кошельки — следующим шагом
(`action_pay`, кусок 2 задачи № 387); здесь её нет намеренно: пока
расчёт можно перепроверить, платить по нему рано.

Доля вкладчика — та же, что видна у него в карточке проекта
(`share_percent`, решение 294): доли вклада, делённые на все доли
проекта. Второй формулы рядом нет, иначе правд снова станет две.

Правил удержания и налога с выплаты пока нет — поле «удержано» равно
нулю. Появятся правила — они лягут в `_withheld_for`, не меняя остального.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

PROFIT_STATES = [
    ('draft', 'Черновик'),
    ('declared', 'Объявлена'),
    ('paid', 'Выплачена'),
    ('disputed', 'Спорная'),
    ('cancelled', 'Отменена'),
]


class CoopProjectProfit(models.Model):
    _name = 'coop.project.profit'
    _description = 'Объявление прибыли проекта'
    _inherit = ['mail.thread']
    _order = 'period_to desc, id desc'

    project_id = fields.Many2one(
        'coop.project', string='Проект', required=True, index=True,
        ondelete='cascade', tracking=True,
        domain=[('kind', 'in', ['commercial', 'dao'])])
    project_kind = fields.Selection(
        related='project_id.kind', string='Вид проекта', store=True)
    initiator_id = fields.Many2one(
        related='project_id.partner_id', string='Инициатор', store=True,
        index=True)
    currency_id = fields.Many2one(
        related='project_id.currency_id', string='Валюта', store=True)
    period_from = fields.Date(string='Период с', required=True, tracking=True)
    period_to = fields.Date(string='Период по', required=True, tracking=True)
    amount = fields.Monetary(
        string='Прибыль к распределению', currency_field='currency_id',
        required=True, tracking=True,
        help='Сколько проект решил разделить между вкладчиками за период.')
    name = fields.Char(string='Название', compute='_compute_name', store=True)
    note = fields.Text(string='Пояснение')
    state = fields.Selection(
        PROFIT_STATES, string='Состояние', default='draft', required=True,
        index=True, tracking=True)
    declared_on = fields.Datetime(string='Объявлена', readonly=True, copy=False)
    declared_by_id = fields.Many2one(
        'res.partner', string='Объявил', readonly=True, copy=False)
    paid_on = fields.Datetime(string='Выплачена', readonly=True, copy=False)
    dispute_reason = fields.Text(string='Суть спора', copy=False)
    line_ids = fields.One2many(
        'coop.project.profit.line', 'profit_id', string='Распределение',
        copy=False)
    line_count = fields.Integer(compute='_compute_totals')
    distributed_total = fields.Monetary(
        string='Распределено', currency_field='currency_id',
        compute='_compute_totals', store=True)
    withheld_total = fields.Monetary(
        string='Удержано', currency_field='currency_id',
        compute='_compute_totals', store=True)
    net_total = fields.Monetary(
        string='К выплате', currency_field='currency_id',
        compute='_compute_totals', store=True)

    @api.depends('project_id.name', 'period_from', 'period_to')
    def _compute_name(self):
        for record in self:
            if record.project_id and record.period_from and record.period_to:
                record.name = _(
                    'Прибыль «%(project)s» за %(start)s — %(end)s',
                    project=record.project_id.name,
                    start=fields.Date.to_string(record.period_from),
                    end=fields.Date.to_string(record.period_to))
            else:
                record.name = _('Прибыль проекта')

    @api.depends('line_ids.amount', 'line_ids.withheld')
    def _compute_totals(self):
        for record in self:
            record.line_count = len(record.line_ids)
            record.distributed_total = sum(record.line_ids.mapped('amount'))
            record.withheld_total = sum(record.line_ids.mapped('withheld'))
            record.net_total = record.distributed_total - record.withheld_total

    @api.constrains('period_from', 'period_to')
    def _check_period(self):
        for record in self:
            if record.period_from > record.period_to:
                raise ValidationError(_(
                    'Период задан наоборот: «с» позже «по».'))

    @api.constrains('amount')
    def _check_amount(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_(
                    'Прибыль к распределению должна быть больше нуля. '
                    'Убыток между вкладчиками этим объявлением не делится.'))

    @api.constrains('project_id')
    def _check_project_kind(self):
        for record in self:
            if record.project_id.kind not in ('commercial', 'dao'):
                raise ValidationError(_(
                    'Прибыль объявляют в коммерческом проекте и в ДАО. '
                    'В кооперативном пай даёт часть результата, а в '
                    'некоммерческом долей нет.'))

    # ── Расчёт ───────────────────────────────────────────────────────────

    def _withheld_for(self, partner, amount):
        """Сколько удержать с суммы вкладчика. Правил пока нет — ноль."""
        return 0.0

    def action_compute(self):
        """Рассчитать строки по долям принятых вкладов.

        Доли берутся на момент расчёта и в строки записываются как
        есть: объявление должно показывать, из чего получилась сумма,
        даже если потом вкладчики и доли изменятся. Остаток от
        округления до копейки отдаётся строке с наибольшей долей —
        иначе распределённая сумма расходилась бы с объявленной.
        """
        for record in self:
            if record.state != 'draft':
                raise UserError(_(
                    'Пересчитать можно только черновик. Объявленную '
                    'прибыль сперва отмените.'))
            project = record.project_id.sudo()
            accepted = project.contribution_ids.filtered(
                lambda c: c.state == 'accepted' and c.share_tokens)
            total = sum(accepted.mapped('share_tokens'))
            if not total:
                raise UserError(_(
                    'В проекте нет принятых вкладов с долями — делить '
                    'прибыль не между кем.'))
            by_partner = {}
            for contribution in accepted:
                by_partner[contribution.partner_id] = (
                    by_partner.get(contribution.partner_id, 0.0)
                    + contribution.share_tokens)
            rounding = record.currency_id.rounding or 0.01
            rows = []
            given = 0.0
            for partner, tokens in sorted(
                    by_partner.items(), key=lambda kv: -kv[1]):
                part = round(record.amount * tokens / total / rounding) * rounding
                part = record.currency_id.round(part)
                given += part
                rows.append([partner, tokens, part])
            if rows:
                rows[0][2] = record.currency_id.round(
                    rows[0][2] + record.amount - given)
            record.line_ids.unlink()
            self.env['coop.project.profit.line'].sudo().create([{
                'profit_id': record.id,
                'partner_id': partner.id,
                'share_tokens': tokens,
                'share_percent': round(tokens / total * 100, 4),
                'amount': part,
                'withheld': record._withheld_for(partner, part),
            } for partner, tokens, part in rows])
        return True

    # ── Состояния ────────────────────────────────────────────────────────

    def action_declare(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Объявить можно только черновик.'))
            if not record.line_ids:
                record.action_compute()
            record.write({
                'state': 'declared',
                'declared_on': fields.Datetime.now(),
                'declared_by_id':
                    self.env.user._coop_acting_partner().id,
            })
            record.message_post(body=_(
                'Прибыль %(amount)s объявлена к распределению между '
                '%(count)s вкладчиками.',
                amount=record.amount, count=len(record.line_ids)))
        return True

    def action_cancel(self):
        for record in self:
            if record.state not in ('draft', 'declared', 'disputed'):
                raise UserError(_(
                    'Отменить можно черновик, объявленную или спорную '
                    'прибыль. Выплаченную отменой не вернуть.'))
            record.state = 'cancelled'
        return True

    def action_dispute(self):
        for record in self:
            if record.state != 'declared':
                raise UserError(_('Оспорить можно объявленную прибыль.'))
            record.state = 'disputed'
        return True

    def action_to_draft(self):
        for record in self:
            if record.state not in ('cancelled', 'disputed'):
                raise UserError(_(
                    'В черновик возвращают отменённую или спорную '
                    'прибыль.'))
            record.write({'state': 'draft', 'declared_on': False,
                          'declared_by_id': False})
        return True


class CoopProjectProfitLine(models.Model):
    _name = 'coop.project.profit.line'
    _description = 'Строка распределения прибыли'
    _order = 'profit_id, amount desc, id'

    profit_id = fields.Many2one(
        'coop.project.profit', string='Объявление', required=True,
        index=True, ondelete='cascade')
    project_id = fields.Many2one(
        related='profit_id.project_id', string='Проект', store=True,
        index=True)
    state = fields.Selection(
        related='profit_id.state', string='Состояние', store=True)
    currency_id = fields.Many2one(
        related='profit_id.currency_id', string='Валюта', store=True)
    partner_id = fields.Many2one(
        'res.partner', string='Вкладчик', required=True, index=True)
    share_tokens = fields.Float(string='Долей', digits=(16, 3))
    share_percent = fields.Float(string='Доля, %', digits=(8, 4))
    amount = fields.Monetary(string='Начислено', currency_field='currency_id')
    withheld = fields.Monetary(string='Удержано', currency_field='currency_id')
    net = fields.Monetary(
        string='К выплате', currency_field='currency_id',
        compute='_compute_net', store=True)

    @api.depends('amount', 'withheld')
    def _compute_net(self):
        for record in self:
            record.net = record.amount - record.withheld

    _one_line_per_partner = models.Constraint(
        'unique(profit_id, partner_id)',
        'Один вкладчик — одна строка в объявлении.',
    )
