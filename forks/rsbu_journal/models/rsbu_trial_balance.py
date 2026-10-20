# -*- coding: utf-8 -*-
"""Оборотно-сальдовая ведомость (ОСВ) по РСБУ-проводкам.

Строится за период по проведённым строкам rsbu.move.line, сгруппированным
по счёту плана счетов. Для каждого счёта показываются шесть показателей:
сальдо на начало (Дт/Кт), обороты за период (Дт/Кт), сальдо на конец
(Дт/Кт) — как в 1С.

Особенности:
  * сальдо активно-пассивных счетов (60/62/76) — РАЗВЁРНУТОЕ (дебиторка и
    кредиторка одновременно), считается в разрезе субконто через
    rsbu.account.get_expanded_balance;
  * иерархия счетов сворачивается снизу вверх: показатели счёта-группы =
    сумма показателей его потомков-листьев;
  * начало года для сальдо — календарное (1 января), результатные счета
    90/91/99 к концу года закрываются регламентом закрытия месяца.

Строки живут в рамках пользовательской сессии (TransientModel); отчёт на
экране (QWeb-HTML) и переход к проводкам (drill-down) строятся поверх них.
"""
from odoo import api, fields, models


class RsbuTrialBalanceLine(models.TransientModel):
    _name = 'rsbu.trial.balance.line'
    _description = 'РСБУ — Строка оборотно-сальдовой ведомости'
    _order = 'code'

    wizard_id = fields.Many2one(
        'rsbu.trial.balance.wizard', string='Отчёт', ondelete='cascade',
        index=True)
    account_id = fields.Many2one('rsbu.account', string='Счёт', index=True)
    code = fields.Char(string='Код счёта', index=True)
    name = fields.Char(string='Наименование счёта')
    level = fields.Integer(string='Уровень')
    is_group = fields.Boolean(string='Счёт-группа')
    parent_code = fields.Char(string='Код родителя')

    company_id = fields.Many2one('res.company', string='Компания')
    currency_id = fields.Many2one('res.currency', string='Валюта')

    opening_debit = fields.Monetary(string='Сальдо нач. Дт',
                                    currency_field='currency_id')
    opening_credit = fields.Monetary(string='Сальдо нач. Кт',
                                     currency_field='currency_id')
    turnover_debit = fields.Monetary(string='Оборот Дт',
                                     currency_field='currency_id')
    turnover_credit = fields.Monetary(string='Оборот Кт',
                                      currency_field='currency_id')
    closing_debit = fields.Monetary(string='Сальдо кон. Дт',
                                    currency_field='currency_id')
    closing_credit = fields.Monetary(string='Сальдо кон. Кт',
                                     currency_field='currency_id')

    def action_open_entries(self):
        """Drill-down: открыть проводки счёта за период отчёта."""
        self.ensure_one()
        wiz = self.wizard_id
        domain = [
            ('account_id', 'child_of', self.account_id.id),
            ('state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
            ('date', '>=', wiz.date_from),
            ('date', '<=', wiz.date_to),
        ]
        return {
            'type': 'ir.actions.act_window',
            'name': '%s %s' % (self.code, self.name or ''),
            'res_model': 'rsbu.move.line',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'search_default_group_account': 0},
        }
