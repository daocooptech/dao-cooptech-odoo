"""Ввод начальных остатков РСБУ-слоя (добавлено пулом, задача 294, К7).

Остатки расчётов на день перед началом учёта в слое — одной операцией в
корреспонденции со вспомогательным счётом 000, как в 1С. Сальдо 62 и 60 по
контрагентам можно взять из бухгалтерии Odoo той же организации.
"""
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RsbuOpeningBalance(models.TransientModel):
    _name = 'rsbu.opening.balance.wizard'
    _description = 'РСБУ — Ввод начальных остатков'

    company_id = fields.Many2one(
        'res.company', string='Организация', required=True,
        default=lambda self: self._default_company())
    date = fields.Date(
        string='Остатки на', required=True,
        compute='_compute_date', store=True, readonly=False, precompute=True,
        help='Последний день перед началом учёта в слое.')
    line_ids = fields.One2many(
        'rsbu.opening.balance.line', 'wizard_id', string='Остатки')

    @api.model
    def _default_company(self):
        companies = self.env.companies.filtered('rsbu_enabled')
        return companies if len(companies) == 1 else self.env['res.company']

    @api.depends('company_id')
    def _compute_date(self):
        for wizard in self:
            start = wizard.company_id.rsbu_start_date
            wizard.date = start - timedelta(days=1) if start                 else fields.Date.context_today(wizard)

    def _account(self, *codes):
        Account = self.env['rsbu.account']
        for code in codes:
            account = Account.search([
                ('company_id', '=', self.company_id.id), ('code', '=', code)],
                limit=1)
            if account:
                return account
        raise UserError(_('В плане счетов организации нет счёта %s.') % codes[0])

    def action_fill_from_accounting(self):
        """Сальдо расчётов с контрагентами из бухгалтерии Odoo на дату."""
        self.ensure_one()
        if not self.company_id or not self.date:
            raise UserError(_('Выберите организацию и дату остатков.'))
        receivable = self._account('62.01', '62')
        payable = self._account('60.01', '60')
        totals = defaultdict(float)
        lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '<=', self.date),
            ('partner_id', '!=', False),
            ('account_id.account_type', 'in',
             ('asset_receivable', 'liability_payable')),
        ])
        for line in lines:
            account = receivable \
                if line.account_id.account_type == 'asset_receivable' else payable
            totals[(account.id, line.partner_id.commercial_partner_id.id)] += line.balance
        rounding = self.company_id.currency_id.rounding or 0.01
        vals = [(5, 0, 0)]
        for (account_id, partner_id), balance in sorted(totals.items()):
            balance = round(balance, 2)
            if abs(balance) < rounding:
                continue
            vals.append((0, 0, {
                'account_id': account_id, 'partner_id': partner_id,
                'debit': balance if balance > 0 else 0.0,
                'credit': -balance if balance < 0 else 0.0,
            }))
        self.line_ids = vals
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name,
            'res_id': self.id, 'view_mode': 'form', 'target': 'new',
        }

    def action_post(self):
        """Провести остатки одной операцией: строки против счёта 000."""
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.debit or l.credit)
        if not lines:
            raise UserError(_('Нет остатков для ввода.'))
        auxiliary = self._account('000')
        move_lines = []
        for line in lines:
            move_lines.append((0, 0, {
                'account_id': line.account_id.id,
                'partner_id': line.partner_id.id,
                'contract_id': line.contract_id.id,
                'debit': line.debit, 'credit': line.credit,
                'name': _('Начальный остаток'),
            }))
        net = round(sum(lines.mapped('debit')) - sum(lines.mapped('credit')), 2)
        if net:
            move_lines.append((0, 0, {
                'account_id': auxiliary.id,
                'debit': -net if net < 0 else 0.0,
                'credit': net if net > 0 else 0.0,
                'name': _('Ввод начальных остатков'),
            }))
        move = self.env['rsbu.move'].create({
            'date': self.date,
            'company_id': self.company_id.id,
            'ref': _('Ввод начальных остатков на %s') % fields.Date.to_string(self.date),
            'line_ids': move_lines,
        })
        move.action_post()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'rsbu.move',
            'res_id': move.id, 'view_mode': 'form',
        }


class RsbuOpeningBalanceLine(models.TransientModel):
    _name = 'rsbu.opening.balance.line'
    _description = 'РСБУ — Строка начального остатка'

    wizard_id = fields.Many2one(
        'rsbu.opening.balance.wizard', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='wizard_id.company_id')
    account_id = fields.Many2one(
        'rsbu.account', string='Счёт', required=True,
        domain="[('company_id', '=', company_id), ('is_group', '=', False)]")
    partner_id = fields.Many2one('res.partner', string='Контрагент')
    contract_id = fields.Many2one('partner.contract.customer', string='Договор')
    debit = fields.Float(string='Дебет', digits=(16, 2))
    credit = fields.Float(string='Кредит', digits=(16, 2))
