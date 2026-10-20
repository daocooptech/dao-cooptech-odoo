"""Регистр промежуточных итогов КУДиР по кварталам (для декларации УСН).

Аналог rsbu.vat.summary: агрегирует записи rsbu.kudir.line за квартал —
доходы и расходы раздела I и уплаченные взносы/пособия раздела IV. Служит
источником для декларации УСН (нарастающим итогом по отчётным периодам).
"""
from odoo import api, fields, models


class RsbuKudirSummary(models.Model):
    _name = 'rsbu.kudir.summary'
    _description = 'РСБУ — Итоги КУДиР за период'
    _order = 'period_key desc'
    _check_company_auto = True

    company_id = fields.Many2one(
        'res.company', string='Компания', required=True, index=True,
        default=lambda self: self.env.company)
    period_key = fields.Char(string='Квартал', required=True, index=True)
    income = fields.Monetary(string='Доходы (раздел I)',
                             currency_field='currency_id')
    expense = fields.Monetary(string='Расходы (раздел I)',
                              currency_field='currency_id')
    insurance = fields.Monetary(string='Взносы/пособия (раздел IV)',
                                currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Валюта',
                                  compute='_compute_currency_id', store=True)

    @api.depends('company_id')
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.company_id.currency_id

    @api.model
    def recompute_period(self, date_from, date_to, company):
        """Пересчитать итоги КУДиР по кварталам периода из записей книги.

        Идемпотентно: сначала пересобирает сами записи КУДиР за период
        (rsbu.kudir.line.recompute_period), затем агрегирует по кварталам.
        """
        Line = self.env['rsbu.kudir.line']
        Line.recompute_period(date_from, date_to, company)
        lines = Line.search([
            ('company_id', '=', company.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ])
        by_period = {}
        for ln in lines:
            data = by_period.setdefault(
                ln.period_key,
                {'income': 0.0, 'expense': 0.0, 'insurance': 0.0})
            if ln.section == 'section_1':
                data['income'] += ln.income_amount
                data['expense'] += ln.expense_amount
            elif ln.section == 'section_4':
                data['insurance'] += ln.expense_amount

        result = self.browse()
        for period_key, data in by_period.items():
            existing = self.search([
                ('company_id', '=', company.id),
                ('period_key', '=', period_key)], limit=1)
            vals = {
                'company_id': company.id,
                'period_key': period_key,
                'income': data['income'],
                'expense': data['expense'],
                'insurance': data['insurance'],
            }
            if existing:
                existing.write(vals)
                result |= existing
            else:
                result |= self.create(vals)
        return result

    @api.model
    def ytd_totals(self, company, year, up_to_quarter):
        """Итоги нарастающим итогом с начала года по квартал включительно.

        Возвращает dict {income, expense, insurance} — сумма по кварталам
        year-Q1 … year-Q{up_to_quarter}. Для декларации УСН (отчётные
        периоды нарастающим итогом).
        """
        keys = ['%s-Q%s' % (year, q) for q in range(1, up_to_quarter + 1)]
        recs = self.search([
            ('company_id', '=', company.id),
            ('period_key', 'in', keys),
        ])
        return {
            'income': round(sum(recs.mapped('income')), 2),
            'expense': round(sum(recs.mapped('expense')), 2),
            'insurance': round(sum(recs.mapped('insurance')), 2),
        }
