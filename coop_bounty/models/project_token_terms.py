# -*- coding: utf-8 -*-
"""Разблокировка по сроку и партии токенов проекта (№ 485, решение 703).

Разблокировка — настройка токена-доли, сертификата и права на прибыль:
начислено сразу, доступно частями. Срок записывается в само начисление:
сменили настройку проекта — прежние начисления живут по своей. Отобрать
начисленное нельзя, закрытое только ждёт своей даты.

Партия — у токена-права требования: одинаковые единицы (абонемент,
билет, ящик урожая) с общим номером и сроком. Держатель меняет токены на
единицу — получает именной талон, и токены гасятся. Отменил инициатор
неиспользованный талон — токены возвращаются.
"""
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .coop_bounty_p2 import _tokens

VEST_KINDS = ('share', 'certificate', 'profit')


class CoopProjectTokenMoveTerms(models.Model):
    _inherit = 'coop.project.token.move'

    vest_cliff = fields.Integer(string='Закрыто первые, мес.', readonly=True)
    vest_months = fields.Integer(string='Открывается частями, мес.', readonly=True)
    ticket_id = fields.Many2one(
        'coop.project.token.ticket', string='Талон', index=True, readonly=True,
        ondelete='restrict')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            project = self.env['coop.project'].sudo().browse(vals.get('project_id'))
            if 'vest_cliff' not in vals and 'vest_months' not in vals \
                    and vals.get('amount', 0) > 0 and not vals.get('ticket_id') \
                    and project.coop_vest and project.coop_token_kind in VEST_KINDS:
                vals['vest_cliff'] = project.coop_vest_cliff
                vals['vest_months'] = project.coop_vest_months
        return super().create(vals_list)

    def _coop_unlocked(self, day=None):
        """Сколько из начисления уже доступно на день."""
        self.ensure_one()
        if not self.vest_cliff and not self.vest_months:
            return self.amount
        day = day or fields.Date.context_today(self)
        gone = relativedelta(day, self.date)
        months = gone.years * 12 + gone.months - self.vest_cliff
        if months < 0:
            return 0
        if not self.vest_months or months >= self.vest_months:
            return self.amount
        return self.amount * months // self.vest_months


class CoopProjectTokenBatch(models.Model):
    _name = 'coop.project.token.batch'
    _description = 'Партия токенов требования'
    _order = 'project_id, date_from desc, id desc'

    project_id = fields.Many2one('coop.project', string='Проект', required=True,
                                 index=True, ondelete='cascade')
    number = fields.Char(string='Номер', readonly=True, copy=False)
    name = fields.Char(string='Что выдаётся', required=True)
    quantity = fields.Integer(string='Единиц', required=True, default=10)
    price = fields.Integer(string='Токенов за единицу', required=True, default=100)
    date_from = fields.Date(string='Действует с', required=True,
                            default=fields.Date.context_today)
    date_to = fields.Date(string='Действует по', required=True)
    ticket_ids = fields.One2many('coop.project.token.ticket', 'batch_id', string='Талоны')
    taken = fields.Integer(string='Взято', compute='_compute_taken', compute_sudo=True)
    used = fields.Integer(string='Погашено', compute='_compute_taken', compute_sudo=True)
    left = fields.Integer(string='Осталось', compute='_compute_taken', compute_sudo=True)
    can_take = fields.Boolean(compute='_compute_can_take')

    _quantity_positive = models.Constraint('check(quantity > 0)', 'Единиц в партии — больше нуля.')
    _price_positive = models.Constraint('check(price > 0)', 'Токенов за единицу — больше нуля.')

    @api.depends('quantity', 'ticket_ids.state')
    def _compute_taken(self):
        for batch in self:
            live = batch.ticket_ids.filtered(lambda t: t.state != 'cancelled')
            batch.taken = len(live)
            batch.used = len(live.filtered(lambda t: t.state == 'used'))
            batch.left = batch.quantity - len(live)

    @api.depends('left', 'price', 'date_to')
    @api.depends_context('uid')
    def _compute_can_take(self):
        today = fields.Date.context_today(self)
        for batch in self:
            batch.can_take = (
                bool(batch._origin.id) and batch.left > 0 and batch.date_to and batch.date_to >= today
                and batch.project_id.coop_token_kind == 'claim'
                and batch.project_id.coop_my_available >= batch.price)

    @api.constrains('project_id')
    def _check_kind(self):
        for batch in self:
            if batch.project_id.coop_token_kind != 'claim':
                raise ValidationError(_('Партии бывают только у токена вида «Право требования».'))

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for batch in self:
            if batch.date_to < batch.date_from:
                raise ValidationError(_('Срок партии заканчивается раньше, чем начинается.'))

    @api.model_create_multi
    def create(self, vals_list):
        batches = super().create(vals_list)
        for batch in batches:
            siblings = self.sudo().with_context(active_test=False).search(
                [('project_id', '=', batch.project_id.id), ('number', '!=', False)])
            last = max([int(n.rsplit('-', 1)[-1]) for n in siblings.mapped('number')] or [0])
            batch.number = '%s-%02d' % (batch.project_id.coop_token_symbol or 'P', last + 1)
        return batches

    def write(self, vals):
        # Под выданные талоны условия не переписываются.
        frozen = {'name', 'price', 'date_from', 'date_to', 'project_id'} & set(vals)
        for batch in self.sudo() if frozen else self.browse():
            changed = [f for f in frozen if batch._fields[f].convert_to_write(batch[f], batch) != vals[f]
                       and str(batch[f]) != str(vals[f])]
            if changed and batch.taken:
                raise UserError(_(
                    'По партии %s уже взяты талоны — условия не меняются. '
                    'Заведите новую партию.', batch.number))
        result = super().write(vals)
        if 'quantity' in vals:
            for batch in self.sudo():
                if batch.left < 0:
                    raise UserError(_('Взято уже %s — единиц в партии меньше быть не может.', batch.taken))
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_without_tickets(self):
        if self.sudo().ticket_ids:
            raise UserError(_('По партии выданы талоны — удалить её нельзя.'))

    def action_take(self):
        """Обменять токены на единицу партии — именной талон."""
        self.ensure_one()
        self.check_access('read')
        holder = self.env.user._coop_acting_partner()
        batch = self.sudo()
        project = batch.project_id
        # Два нажатия разом не должны потратить одни токены дважды.
        self.env.cr.execute('SELECT id FROM coop_project WHERE id = %s FOR UPDATE', [project.id])
        self.env.invalidate_all()
        today = fields.Date.context_today(self)
        if project.coop_token_kind != 'claim':
            raise UserError(_('Токен проекта — не право требования.'))
        if batch.date_to < today:
            raise UserError(_('Срок партии %s прошёл.', batch.number))
        if batch.left <= 0:
            raise UserError(_('Партия %s разобрана.', batch.number))
        available = project._coop_holder_balance(holder)[1]
        if available < batch.price:
            raise UserError(_(
                'Не хватает токенов: нужно %(need)s, доступно %(have)s %(unit)s.',
                need=_tokens(batch.price), have=_tokens(available),
                unit=project._coop_token_unit()))
        ticket = batch.env['coop.project.token.ticket'].create({
            'batch_id': batch.id, 'partner_id': holder.id, 'taken_on': today,
            'number': '%s-%04d' % (batch.number, len(batch.ticket_ids) + 1)})
        batch.env['coop.project.token.move'].create({
            'project_id': project.id, 'partner_id': holder.id, 'amount': -batch.price,
            'date': today, 'ticket_id': ticket.id,
            'description': _('Талон %(number)s: %(name)s', number=ticket.number, name=batch.name)})
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': _('Талон %s ваш.', ticket.number),
                       'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }


class CoopProjectTokenTicket(models.Model):
    _name = 'coop.project.token.ticket'
    _description = 'Талон партии'
    _order = 'taken_on desc, id desc'
    _rec_name = 'number'

    number = fields.Char(string='Талон', required=True, readonly=True)
    batch_id = fields.Many2one('coop.project.token.batch', string='Партия', required=True,
                               readonly=True, index=True, ondelete='restrict')
    project_id = fields.Many2one(related='batch_id.project_id', store=True, index=True)
    batch_name = fields.Char(related='batch_id.name', string='Что выдаётся', related_sudo=True)
    date_to = fields.Date(related='batch_id.date_to', string='Действует по')
    partner_id = fields.Many2one('res.partner', string='Держатель', required=True,
                                 readonly=True, index=True)
    taken_on = fields.Date(string='Взят', required=True, readonly=True)
    used_on = fields.Date(string='Погашен', readonly=True)
    state = fields.Selection([
        ('active', 'Действует'),
        ('used', 'Погашен'),
        ('cancelled', 'Отменён'),
    ], string='Состояние', required=True, default='active', readonly=True, index=True)
    status = fields.Selection([
        ('active', 'Действует'),
        ('used', 'Погашен'),
        ('expired', 'Срок вышел'),
        ('cancelled', 'Отменён'),
    ], string='Статус', compute='_compute_status')
    can_manage = fields.Boolean(compute='_compute_can_manage')

    _number_unique = models.Constraint('unique(number)', 'Талон с таким номером уже есть.')

    @api.depends('state', 'date_to')
    def _compute_status(self):
        today = fields.Date.context_today(self)
        for ticket in self:
            ticket.status = 'expired' if (
                ticket.state == 'active' and ticket.date_to and ticket.date_to < today) else ticket.state

    @api.depends_context('uid')
    def _compute_can_manage(self):
        for ticket in self:
            ticket.can_manage = ticket.project_id.has_access('write')

    def _coop_check_issuer(self):
        for ticket in self:
            if not ticket.project_id.has_access('write'):
                raise AccessError(_('Талон гасит и отменяет инициатор проекта.'))
            if ticket.state != 'active':
                raise UserError(_('Талон %s уже не действует.', ticket.number))

    def action_use(self):
        self._coop_check_issuer()
        for ticket in self.sudo():
            if ticket.status == 'expired':
                raise UserError(_('Срок талона %s вышел.', ticket.number))
            if ticket.batch_id.date_from > fields.Date.context_today(self):
                raise UserError(_('Талон %s ещё не действует.', ticket.number))
            ticket.write({'state': 'used', 'used_on': fields.Date.context_today(self)})
        return True

    def action_cancel(self):
        """Проект не может исполнить — токены возвращаются держателю."""
        self._coop_check_issuer()
        for ticket in self.sudo():
            ticket.state = 'cancelled'
            ticket.env['coop.project.token.move'].create({
                'project_id': ticket.project_id.id, 'partner_id': ticket.partner_id.id,
                'amount': ticket.batch_id.price, 'ticket_id': ticket.id,
                'date': fields.Date.context_today(self),
                'description': _('Талон %s отменён — токены возвращены', ticket.number)})
        return True


class CoopProjectTokenTerms(models.Model):
    _inherit = 'coop.project'

    coop_vest = fields.Boolean(
        string='Разблокировка по сроку',
        help='Начисленное доступно частями. Начисленное до включения доступно сразу.')
    coop_vest_cliff = fields.Integer(
        string='Закрыто первые, мес.', default=3,
        help='Первые месяцы после начисления закрыто всё.')
    coop_vest_months = fields.Integer(
        string='Потом частями, мес.', default=12,
        help='Затем открывается поровну каждый месяц. Ноль — открывается сразу всё.')
    coop_batch_ids = fields.One2many('coop.project.token.batch', 'project_id', string='Партии')
    coop_ticket_ids = fields.One2many('coop.project.token.ticket', 'project_id', string='Талоны')
    coop_my_tokens = fields.Integer(string='У вас токенов', compute='_compute_coop_my_tokens')
    coop_my_available = fields.Integer(string='Доступно', compute='_compute_coop_my_tokens')
    coop_my_locked = fields.Integer(string='Откроется позже', compute='_compute_coop_my_tokens')

    @api.constrains('coop_vest', 'coop_vest_cliff', 'coop_vest_months')
    def _check_coop_vest(self):
        for project in self.filtered('coop_vest'):
            if not 0 <= project.coop_vest_cliff <= 60 or not 0 <= project.coop_vest_months <= 120:
                raise ValidationError(_(
                    'Срок разблокировки: закрыто — до 60 месяцев, частями — до 120.'))
            if not project.coop_vest_cliff and not project.coop_vest_months:
                raise ValidationError(_('Задайте срок разблокировки — хотя бы один месяц.'))

    def _coop_holder_balance(self, partner, day=None):
        """Сколько у держателя всего и сколько доступно."""
        self.ensure_one()
        if not self._origin.id or not partner:
            return 0, 0
        moves = self.env['coop.project.token.move'].sudo().search([
            ('project_id', '=', self._origin.id), ('partner_id', '=', partner.id)])
        total = sum(moves.mapped('amount'))
        return total, max(sum(move._coop_unlocked(day) for move in moves), 0)

    @api.depends_context('uid')
    def _compute_coop_my_tokens(self):
        holder = self.env.user._coop_acting_partner()
        for project in self:
            total, available = project._coop_holder_balance(holder)
            project.coop_my_tokens = total
            project.coop_my_available = available
            project.coop_my_locked = total - available
