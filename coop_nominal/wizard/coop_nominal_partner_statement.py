# -*- coding: utf-8 -*-
import csv
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes


def _money(value):
    # Таблица открывается в Excel с русскими настройками: запятая в дробях.
    return ('%.2f' % value).replace('.', ',') if value else ''


class CoopNominalPartnerStatement(models.TransientModel):
    """Выписка участника по номинальному счёту за период.

    Строки — записи книги, где участник бенефициар: пришли деньги, перешли
    к продавцу по акту, удержана комиссия, ушла выплата. Остаток на начало
    и на конец — по той же книге, поэтому выписка сходится с реестром
    оператора копейка в копейку.
    """
    _name = 'coop.nominal.partner.statement'
    _description = 'Выписка по безопасным сделкам за период'

    wallet_id = fields.Many2one('coop.wallet', string='Кошелёк', required=True)
    partner_id = fields.Many2one(related='wallet_id.partner_id')
    date_from = fields.Date(
        string='С', required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        string='По', required=True, default=fields.Date.context_today)
    file = fields.Binary(string='Файл', readonly=True, attachment=False)
    file_name = fields.Char(string='Имя файла', readonly=True)

    @api.constrains('date_from', 'date_to')
    def _check_period(self):
        for record in self:
            if record.date_from > record.date_to:
                raise UserError(_('Начало периода позже конца.'))

    def _rows(self):
        """Остаток на начало, строки периода с остатком после каждой и
        остаток на конец."""
        self.ensure_one()
        # Кошелёк читает только его хозяин и казначеи организации: проверили
        # доступ — книгу его бенефициара можно читать целиком.
        self.wallet_id.check_access('read')
        Entry = self.env['coop.nominal.entry'].sudo()
        base = [('leg', '=', 'holder'), ('partner_id', '=', self.partner_id.id)]
        opening = -sum(Entry.search(base + [('date', '<', self.date_from)]).mapped('amount'))
        entries = Entry.search(base + [
            ('date', '>=', self.date_from), ('date', '<=', self.date_to)])
        kinds = dict(Entry._fields['kind']._description_selection(self.env))
        balance = opening
        rows = []
        for entry in entries:
            hold = entry.hold_id
            other = hold.payee_id if hold.payer_id == self.partner_id else hold.payer_id
            change = -entry.amount
            balance += change
            rows.append({
                'date': entry.date,
                'code': hold.code or '',
                'deal': hold.deal_id.name or '',
                'other': other.name or '',
                'kind': kinds.get(entry.kind, entry.kind),
                'income': change if change > 0 else 0.0,
                'expense': -change if change < 0 else 0.0,
                'balance': balance,
            })
        return opening, rows, balance

    def _csv(self):
        opening, rows, closing = self._rows()
        out = io.StringIO()
        writer = csv.writer(out, delimiter=';', lineterminator='\r\n')
        fmt = lambda d: d.strftime('%d.%m.%Y')
        writer.writerow([_('Выписка по безопасным сделкам на номинальном счёте')])
        writer.writerow([_('Участник'), self.partner_id.name])
        writer.writerow([_('Период'), '%s — %s' % (fmt(self.date_from), fmt(self.date_to))])
        writer.writerow([])
        writer.writerow([_('Дата'), _('Удержание'), _('Сделка'), _('Другая сторона'),
                         _('Событие'), _('Приход'), _('Расход'), _('Остаток')])
        writer.writerow(['', '', '', '', _('Остаток на начало'), '', '', _money(opening) or '0,00'])
        for row in rows:
            writer.writerow([fmt(row['date']), row['code'], row['deal'], row['other'],
                             row['kind'], _money(row['income']), _money(row['expense']),
                             _money(row['balance']) or '0,00'])
        writer.writerow(['', '', '', '', _('Итого за период'),
                         _money(sum(r['income'] for r in rows)) or '0,00',
                         _money(sum(r['expense'] for r in rows)) or '0,00', ''])
        writer.writerow(['', '', '', '', _('Остаток на конец'), '', '', _money(closing) or '0,00'])
        # Метка порядка байтов — чтобы Excel узнал UTF-8 и не исказил кириллицу.
        return ('﻿' + out.getvalue()).encode('utf-8')

    def action_download(self):
        self.ensure_one()
        file_name = 'statement_%s_%s.csv' % (
            self.date_from.strftime('%Y%m%d'), self.date_to.strftime('%Y%m%d'))
        self.write({
            'file': BinaryBytes(self._csv(), filename=file_name),
            'file_name': file_name,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/file/%s?download=true' % (
                self._name, self.id, self.file_name),
            'target': 'self',
        }
