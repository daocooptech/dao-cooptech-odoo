from odoo import models, fields, api
from datetime import datetime
import re
from pytils import numeral, dt
from odoo.tools import pycompat


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    amount_total_words = fields.Char(
        string='Сумма прописью',
        compute='_compute_amount_total_words',
        store=True
    )

    chief_initials = fields.Char(
        string='Инициалы руководителя',
        compute='_compute_chief_initials',
        store=True
    )

    accountant_initials = fields.Char(
        string='Инициалы бухгалтера',
        compute='_compute_accountant_initials',
        store=True
    )

    @api.depends('company_id.chief_id.name')
    def _compute_chief_initials(self):
        for order in self:
            if order.company_id and order.company_id.chief_id:
                order.chief_initials = self._get_initials(order.company_id.chief_id.name)
            else:
                order.chief_initials = ''

    @api.depends('company_id.accountant_id.name')
    def _compute_accountant_initials(self):
        for order in self:
            if order.company_id and order.company_id.accountant_id:
                order.accountant_initials = self._get_initials(order.company_id.accountant_id.name)
            else:
                order.accountant_initials = ''

    def _get_initials(self, fio):
        if fio:
            # fio.split()[0]
            # [fio[0:1]+'.' for fio in fio.split()[1:]]
            return (fio.split()[0] + ' ' + ''.join([part[0:1] + '.' for part in fio.split()[1:]])).strip()
        return ''

    @api.depends('amount_total')
    def _compute_amount_total_words(self):
        for order in self:
            if order.amount_total:
                order.amount_total_words = self.rubles(order.amount_total)
            else:
                order.amount_total_words = ''

    def rubles(self, sum_amount):
        rub = int(sum_amount)
        kop = int(round((sum_amount - rub) * 100))

        text_rubles = numeral.rubles(rub)
        text_copeck = numeral.choose_plural(kop, ("копейка", "копейки", "копеек"))
        text_rubles = text_rubles[0].upper() + text_rubles[1:]

        return ("%s %02d %s") % (text_rubles, kop, text_copeck)

    def print_quotation(self):
        self.filtered(lambda s: s.state == 'draft').write({'state': 'sent'})
        return self.env['report'].get_action(self, 'l10n_ru_doc.report_order')

