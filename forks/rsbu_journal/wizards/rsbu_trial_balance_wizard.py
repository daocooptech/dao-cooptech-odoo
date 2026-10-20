# -*- coding: utf-8 -*-
"""Мастер формирования оборотно-сальдовой ведомости (ОСВ)."""
from datetime import timedelta

from odoo import api, fields, models
from odoo.tools import float_is_zero


class RsbuTrialBalanceWizard(models.TransientModel):
    _name = 'rsbu.trial.balance.wizard'
    _description = 'РСБУ — Мастер оборотно-сальдовой ведомости'

    company_id = fields.Many2one(
        'res.company', string='Компания', required=True,
        default=lambda self: self.env.company)
    date_from = fields.Date(
        string='Период с', required=True,
        default=lambda self: fields.Date.today().replace(month=1, day=1))
    date_to = fields.Date(
        string='Период по', required=True,
        default=lambda self: fields.Date.today())
    hide_zero = fields.Boolean(
        string='Скрывать счета без данных', default=True,
        help='Не показывать счета с нулевыми сальдо и оборотами.')
    only_posted = fields.Boolean(
        string='Только проведённые', default=True, readonly=True,
        help='ОСВ строится по проведённым проводкам (иных в РСБУ-журнале '
             'к учёту не принимается).')
    line_ids = fields.One2many(
        'rsbu.trial.balance.line', 'wizard_id', string='Строки ОСВ')

    # ------------------------------------------------------------------
    def _iter_accounts(self):
        """Счета компании для ОСВ (все, порядок по коду)."""
        self.ensure_one()
        return self.env['rsbu.account'].search([
            ('company_id', '=', self.company_id.id),
        ], order='complete_code, code')

    def _account_values(self, account):
        """Шесть показателей ОСВ по счёту (развёрнутое сальдо для АП)."""
        self.ensure_one()
        cid = self.company_id.id
        day_before = self.date_from - timedelta(days=1)
        # Сальдо на начало (до date_from) — развёрнутое по субконто.
        opening = account.get_expanded_balance(
            date_to=day_before, company_id=cid)
        # Обороты за период (по поддереву счёта).
        turnover = account.get_turnover(
            date_from=self.date_from, date_to=self.date_to,
            company_id=cid, include_children=True)
        # Сальдо на конец (до date_to включительно) — развёрнутое.
        closing = account.get_expanded_balance(
            date_to=self.date_to, company_id=cid)
        return {
            'opening_debit': opening['debit'],
            'opening_credit': opening['credit'],
            'turnover_debit': turnover['debit'],
            'turnover_credit': turnover['credit'],
            'closing_debit': closing['debit'],
            'closing_credit': closing['credit'],
        }

    def _is_zero_row(self, vals):
        rounding = self.company_id.currency_id.rounding or 0.01
        return all(float_is_zero(vals[f], precision_rounding=rounding)
                   for f in ('opening_debit', 'opening_credit',
                             'turnover_debit', 'turnover_credit',
                             'closing_debit', 'closing_credit'))

    def action_generate(self):
        """Пересчитать строки ОСВ и открыть отчёт на экране (QWeb-HTML)."""
        self.ensure_one()
        self.line_ids.unlink()
        Line = self.env['rsbu.trial.balance.line']
        currency = self.company_id.currency_id
        vals_list = []
        for account in self._iter_accounts():
            vals = self._account_values(account)
            if self.hide_zero and self._is_zero_row(vals):
                continue
            vals.update({
                'wizard_id': self.id,
                'account_id': account.id,
                'code': account.code,
                'name': account.name,
                'level': account.level,
                'is_group': bool(account.child_ids),
                'parent_code': account.parent_id.code or False,
                'company_id': self.company_id.id,
                'currency_id': currency.id,
            })
            vals_list.append(vals)
        Line.create(vals_list)
        return self.action_view_report()

    def action_view_report(self):
        """Открыть отчёт ОСВ (QWeb-HTML) для текущего мастера."""
        self.ensure_one()
        return self.env.ref(
            'rsbu_journal.action_report_rsbu_trial_balance').report_action(self)

    # ------------------------------------------------------------------
    def _report_totals(self):
        """Итоги ОСВ — только по счетам верхнего уровня (без двойного счёта).

        Итог считается по корневым счетам (level 0), чтобы не суммировать
        родителя и его потомков дважды.
        """
        self.ensure_one()
        roots = self.line_ids.filtered(lambda l: not l.parent_code)
        return {
            'opening_debit': sum(roots.mapped('opening_debit')),
            'opening_credit': sum(roots.mapped('opening_credit')),
            'turnover_debit': sum(roots.mapped('turnover_debit')),
            'turnover_credit': sum(roots.mapped('turnover_credit')),
            'closing_debit': sum(roots.mapped('closing_debit')),
            'closing_credit': sum(roots.mapped('closing_credit')),
        }
