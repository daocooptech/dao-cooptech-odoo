"""Автосоздание счёта-фактуры на аванс при поступлении аванса от покупателя.

Плательщик УСН, исчисляющий НДС, при получении аванса обязан начислить
авансовый НДС и выставить счёт-фактуру на аванс. В РСБУ-слое этому
соответствует rsbu.invoice(advance), порождающий проводку Дт 76.АВ —
Кт 68.02. Здесь такой СФ создаётся автоматически при проведении платежа,
если поступление образует аванс по облагаемой НДС сделке.
"""
from odoo import models

# Ставочные режимы НДС на УСН (при них начисляется авансовый НДС).
_VAT_RATE_MODES = ('vat_5', 'vat_7')


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        res = super().action_post()
        for payment in self.filtered(
                lambda p: p.state in ('in_process', 'paid')):
            payment._rsbu_autocreate_advance_invoice()
        return res

    def _rsbu_autocreate_advance_invoice(self):
        """Создать и подтвердить авансовый СФ по поступившему авансу.

        Условия: входящий клиентский платёж, породивший аванс (Кт счёта
        advance_received в РСБУ-проводке); режим НДС компании — ставочный;
        сделка облагается НДС (инвойс источник правды). Не выполняется для
        калибровочных проводок (их авансовые СФ строит калибровочный слой)
        и идемпотентно (повторно СФ по той же проводке-авансу не создаётся).
        """
        self.ensure_one()
        if self.env.context.get('rsbu_skip'):
            return
        # Калибровочные документы размечает калибровочный слой.
        if getattr(self, '_rsbu_is_calibration', None) \
                and self._rsbu_is_calibration():
            return
        if self.company_id.rsbu_vat_mode not in _VAT_RATE_MODES:
            return
        move = self.rsbu_move_id
        if not move:
            return
        # Облагаемость: инвойс того же контрагента/договора с НДС.
        if not (getattr(self, '_rsbu_payment_is_taxable', None)
                and self._rsbu_payment_is_taxable()):
            return

        Invoice = self.env['rsbu.invoice'].sudo()
        advance_acc = Invoice._role_account_for_company(
            'advance_received', self.company_id)
        if not advance_acc:
            return
        # Строки-авансы этой проводки (Кт advance_received, origin = сама
        # проводка). По каждому авансу — свой СФ (дроблёный вычет по origin).
        advance_lines = move.line_ids.filtered(
            lambda l: l.account_id == advance_acc and l.credit > 0)
        for line in advance_lines:
            origin = line.origin_move_id or move
            # Идемпотентность: СФ по этому авансу-основанию уже есть.
            if Invoice.search_count([
                    ('origin_move_id', '=', origin.id),
                    ('invoice_type', '=', 'advance'),
                    ('company_id', '=', self.company_id.id)]):
                continue
            invoice = Invoice.create({
                'invoice_type': 'advance',
                'partner_id': line.partner_id.id or self.partner_id.id,
                'company_id': self.company_id.id,
                'date': move.date,
                'base_amount': line.credit,
                'origin_move_id': origin.id,
            })
            invoice.action_confirm()
