# -*- coding: utf-8 -*-
"""Данные для печатной формы акта сверки (DOCX, движок docx_report).

Публичные методы act_docx_* вызываются из docxtpl-шаблона (через кастомные
переменные), чтобы собрать стороны, строки операций и итоги.
"""
from odoo import _, models
from odoo.exceptions import UserError


class RuodooRsbuActDocx(models.Model):
    _inherit = 'ruodoo.rsbu.act'

    @staticmethod
    def _party(partner, name=None):
        return {
            'name': name or partner.name or '',
            'inn': (partner.inn or '').strip(),
            'kpp': (getattr(partner, 'kpp', '') or '').strip(),
            'ogrn': (getattr(partner, 'ogrn', '') or '').strip(),
        }

    def act_docx_seller(self):
        self.ensure_one()
        return self._party(self.company_id.partner_id, self.company_id.name)

    def act_docx_buyer(self):
        self.ensure_one()
        return self._party(self.partner_id)

    def act_docx_lines(self):
        """Операции акта для таблицы DOCX."""
        self.ensure_one()
        rows = []
        for idx, line in enumerate(self.line_ids, start=1):
            rows.append({
                'num': idx,
                'date': line.date.strftime('%d.%m.%Y') if line.date else '',
                'name': line.name or line.doc_name or '',
                'doc': ('%s %s' % (line.doc_name or '', line.doc_number or '')
                        ).strip(),
                'debit': line.debit,
                'credit': line.credit,
            })
        return rows

    def act_docx_totals(self):
        self.ensure_one()
        return {
            'opening_debit': self.opening_debit,
            'opening_credit': self.opening_credit,
            'turnover_debit': self.turnover_debit,
            'turnover_credit': self.turnover_credit,
            'closing_debit': self.closing_debit,
            'closing_credit': self.closing_credit,
        }

    def act_docx_signer(self):
        self.ensure_one()
        signer = self.company_id.rsbu_signatory_id or getattr(
            self.company_id, 'chief_id', False)
        name = signer.partner_id.name if signer else ''
        function = (signer.partner_id.function if signer else '') or (
            getattr(self.company_id, 'rsbu_signatory_title', '')
            or 'Руководитель')
        return {'name': name, 'function': function}

    def act_docx_summary(self):
        """Итоговая формулировка задолженности на конец периода."""
        self.ensure_one()
        if self.closing_debit:
            return ('По данным %s задолженность в пользу %s составляет '
                    '%.2f руб.' % (self.company_id.name,
                                   self.company_id.name, self.closing_debit))
        if self.closing_credit:
            return ('По данным %s задолженность в пользу %s составляет '
                    '%.2f руб.' % (self.company_id.name,
                                   self.partner_id.name, self.closing_credit))
        return 'На конец периода задолженность отсутствует.'

    # ------------------------------------------------------------------
    def action_print_docx(self):
        """Печать акта сверки в DOCX."""
        self.ensure_one()
        if self.state == 'draft':
            self.action_compute()
        template = self.env.ref(
            'ruodoo_rsbu_act.docx_template_act', raise_if_not_found=False)
        if not template:
            raise UserError(_('Не найден DOCX-шаблон акта сверки.'))
        return template.report_id.report_action(self)
