# -*- coding: utf-8 -*-
"""Отчётная модель ОСВ (QWeb-HTML на экран)."""
from odoo import api, models


class RsbuTrialBalanceReport(models.AbstractModel):
    _name = 'report.rsbu_journal.report_rsbu_trial_balance'
    _description = 'РСБУ — Отчёт ОСВ'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['rsbu.trial.balance.wizard'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'rsbu.trial.balance.wizard',
            'docs': wizards,
            'totals_by_wizard': {w.id: w._report_totals() for w in wizards},
        }
