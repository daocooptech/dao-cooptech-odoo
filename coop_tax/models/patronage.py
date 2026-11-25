# -*- coding: utf-8 -*-
"""Патронаж: участие каждого члена в году и начисление по нему (решение 703).

Делитель — сумму к распределению и базы — видят все члены (решение 659
п. 2), а строка участия — только сам член и те, кто ведёт счета
кооператива. Участие не передаётся: это учёт кооператива, а не токен на
руках. Начисление идёт на паевой счёт заявкой и проводится решением
органа управления; потолок года сверяется при проведении (решение 517).
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round


class CoopTaxPayoutMember(models.Model):
    _name = 'coop.tax.payout.member'
    _description = 'Участие члена кооператива за год'
    _order = 'limit_id, amount desc, id'

    limit_id = fields.Many2one(
        'coop.tax.payout.limit', string='Год', required=True, index=True, ondelete='cascade')
    account_id = fields.Many2one(
        'coop.share.account', string='Паевой счёт', required=True, index=True, ondelete='cascade')
    partner_id = fields.Many2one(related='account_id.partner_id', store=True, index=True, string='Член')
    currency_id = fields.Many2one(related='limit_id.currency_id')
    labor_hours = fields.Float(string='Труд, ч', digits=(16, 1))
    turnover = fields.Monetary(string='Оборот', currency_field='currency_id')
    shares = fields.Monetary(string='Пай на конец года', currency_field='currency_id')
    amount = fields.Monetary(
        string='Причитается', currency_field='currency_id', compute='_compute_amount', store=True)
    move_id = fields.Many2one('coop.share.move', string='Начисление', readonly=True, ondelete='set null')
    move_state = fields.Selection(related='move_id.state', string='Состояние начисления', related_sudo=True)

    _member_unique = models.Constraint(
        'unique(limit_id, account_id)', 'Участие этого члена за год уже внесено.')

    @api.depends('labor_hours', 'turnover', 'shares', 'limit_id.distribute_total',
                 'limit_id.pct_labor', 'limit_id.pct_turnover', 'limit_id.pct_share',
                 'limit_id.base_labor_hours', 'limit_id.base_turnover', 'limit_id.member_ids.shares')
    def _compute_amount(self):
        for line in self:
            limit = line.limit_id.sudo()
            base_shares = sum(limit.member_ids.mapped('shares'))
            amount = 0.0
            for pct, value, base in (
                    (limit.pct_labor, line.labor_hours, limit.base_labor_hours),
                    (limit.pct_turnover, line.turnover, limit.base_turnover),
                    (limit.pct_share, line.shares, base_shares)):
                if base:
                    amount += limit.distribute_total * pct / 100 * value / base
            # Вниз до копейки: вместе строки не превысят распределяемого.
            line.amount = float_round(amount, precision_digits=2, rounding_method='DOWN')

    @api.constrains('labor_hours', 'turnover', 'shares')
    def _check_positive(self):
        for line in self:
            if line.labor_hours < 0 or line.turnover < 0 or line.shares < 0:
                raise ValidationError(_('Труд, оборот и пай — не меньше нуля.'))

    @api.constrains('account_id', 'limit_id')
    def _check_cooperative(self):
        for line in self:
            if line.account_id.sudo().cooperative_id != line.limit_id.cooperative_id:
                raise ValidationError(_('Паевой счёт другого кооператива.'))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.limit_id._coop_sync_bases()
        return lines

    def write(self, vals):
        measured = {'labor_hours', 'turnover', 'shares', 'account_id', 'limit_id'} & set(vals)
        if measured and self.sudo().limit_id.member_ids.move_id:
            raise UserError(_('По итогам года уже начислено — участие не меняется.'))
        result = super().write(vals)
        if measured:
            self.limit_id._coop_sync_bases()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_not_accrued(self):
        if self.sudo().move_id:
            raise UserError(_('По строке уже начислено — удалить её нельзя.'))

    def unlink(self):
        limits = self.limit_id
        result = super().unlink()
        limits.exists()._coop_sync_bases()
        return result


class CoopTaxPayoutLimitPatronage(models.Model):
    _inherit = 'coop.tax.payout.limit'

    member_ids = fields.One2many('coop.tax.payout.member', 'limit_id', string='Участие членов')
    distribute_basis = fields.Char(
        string='Решение о распределении', help='Протокол общего собрания, номер и дата.')
    coop_can_edit = fields.Boolean(compute='_compute_coop_can_edit')
    coop_accrued_lines = fields.Boolean(compute='_compute_coop_accrued_lines', compute_sudo=True)

    @api.depends_context('uid')
    def _compute_coop_can_edit(self):
        for record in self:
            record.coop_can_edit = not record._origin.id or record.has_access('write')

    @api.depends('member_ids.move_id')
    def _compute_coop_accrued_lines(self):
        for record in self:
            record.coop_accrued_lines = bool(record.member_ids.move_id)

    def write(self, vals):
        frozen = {'distribute_total', 'pct_labor', 'pct_turnover', 'pct_share',
                  'base_labor_hours', 'base_turnover', 'cooperative_id', 'year'} & set(vals)
        for record in self.sudo() if frozen else self.browse():
            if record.member_ids.move_id and any(
                    (record[f].id if f == 'cooperative_id' else record[f]) != vals[f] for f in frozen):
                raise UserError(_('По итогам года уже начислено — распределение не меняется.'))
        return super().write(vals)

    def _coop_sync_bases(self):
        """Базы — сумма строк: делитель и участие не расходятся."""
        for record in self.sudo():
            if record.member_ids and not record.member_ids.move_id:
                record.write({
                    'base_labor_hours': sum(record.member_ids.mapped('labor_hours')),
                    'base_turnover': sum(record.member_ids.mapped('turnover'))})

    def _coop_turnover(self, partner):
        """Завершённые за год сделки члена с кооперативом."""
        self.ensure_one()
        pair = [self.cooperative_id.id, partner.id]
        return sum(self.env['coop.deal'].sudo().search([
            ('state', '=', 'done'), ('party_a_id', 'in', pair), ('party_b_id', 'in', pair),
            ('closed_on', '>=', '%s-01-01' % self.year),
            ('closed_on', '<=', '%s-12-31' % self.year)]).mapped('amount'))

    def action_collect_members(self):
        """Собрать участие: члены, оборот по сделкам, пай на конец года.

        Оборот, внесённый вручную, не затирается: через платформу идёт не
        вся торговля кооператива. Часы труда вносит кооператив.
        """
        for record in self:
            record.check_access('write')
            record = record.sudo()
            if record.member_ids.move_id:
                raise UserError(_('По итогам года уже начислено — участие не меняется.'))
            end = '%s-12-31' % record.year
            accounts = self.env['coop.share.account'].sudo().search([
                ('cooperative_id', '=', record.cooperative_id.id),
                '|', ('joined_on', '=', False), ('joined_on', '<=', end)])
            known = {line.account_id.id: line for line in record.member_ids}
            for account in accounts:
                shares = max(sum(account.move_ids.filtered(
                    lambda m: m.state == 'confirmed' and str(m.date) <= end
                    and m.kind in ('share', 'extra', 'in_kind', 'return')).mapped('amount')), 0.0)
                turnover = record._coop_turnover(account.partner_id)
                line = known.get(account.id)
                if line:
                    values = {'shares': shares}
                    if not line.turnover:
                        values['turnover'] = turnover
                    line.write(values)
                else:
                    record.member_ids.create({
                        'limit_id': record.id, 'account_id': account.id,
                        'shares': shares, 'turnover': turnover})
        return True

    def action_accrue_members(self):
        """Начислить по участию — заявками на паевые счета."""
        Move = self.env['coop.share.move'].sudo()
        for record in self:
            record.check_access('write')
            record = record.sudo()
            if not record.distribute_total:
                raise UserError(_('Внесите сумму к распределению — её решает собрание.'))
            if not record.distribute_basis:
                raise UserError(_('Укажите решение о распределении: протокол, номер и дата.'))
            if not record.member_ids:
                raise UserError(_('Сначала соберите участие членов.'))
            if record.member_ids.move_id:
                raise UserError(_('По итогам %s года уже начислено.', record.year))
            accrued = Move.search([
                ('kind', '=', 'accrual'), ('state', '!=', 'declined'),
                ('account_id.cooperative_id', '=', record.cooperative_id.id),
                ('coop_result_year', '=', record.year)], limit=1)
            if accrued:
                raise UserError(_(
                    'За %s год начисления уже внесены вручную — второй раз не начисляем.',
                    record.year))
            if not any(line.amount > 0 for line in record.member_ids):
                raise UserError(_('Начислять нечего: участия нет.'))
            for line in record.member_ids.filtered(lambda l: l.amount > 0):
                line.move_id = Move.create({
                    'account_id': line.account_id.id, 'kind': 'accrual', 'state': 'requested',
                    'name': _('Кооперативная выплата за %s год', record.year),
                    'basis': record.distribute_basis, 'amount': line.amount,
                    'coop_result_year': record.year})
        return True
