# -*- coding: utf-8 -*-
import hashlib

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Выплата «живая», пока может дойти до банка или уже ушла и ответа нет.
LIVE = ('queued', 'bank_review', 'sent', 'unknown')


class CoopNominalPayout(models.Model):
    """Распоряжение выплатить долю получателю или вернуть плательщику.

    Выплата исполнена, только когда списание видно в выписке: ответ банка
    «принято» — ещё не деньги у получателя. На долю — одна живая выплата,
    иначе повтор после сбоя заплатил бы дважды.
    """
    _name = 'coop.nominal.payout'
    _description = 'Выплата с номинального счёта'
    _inherit = ['mail.thread']
    _order = 'id desc'

    share_id = fields.Many2one(
        'coop.nominal.share', string='Доля', required=True,
        ondelete='restrict', index=True)
    account_id = fields.Many2one(
        related='share_id.account_id', store=True, index=True, string='Счёт')
    kind = fields.Selection([
        ('payout', 'Выплата получателю'),
        ('refund', 'Возврат плательщику'),
    ], string='Вид', required=True)
    partner_id = fields.Many2one(
        'res.partner', string='Кому', required=True, index=True)
    amount = fields.Monetary(
        string='Сумма', currency_field='currency_id', required=True)
    currency_id = fields.Many2one(related='share_id.currency_id')
    state = fields.Selection([
        ('queued', 'В очереди'),
        ('bank_review', 'На проверке банка'),
        ('sent', 'Отправлено в банк'),
        ('unknown', 'Ответа нет'),
        ('executed', 'Списано по выписке'),
        ('failed', 'Отклонено'),
        ('cancelled', 'Снято'),
    ], string='Состояние', default='queued', required=True, index=True,
        tracking=True)
    version = fields.Integer(string='Попытка', readonly=True)
    idempotency_key = fields.Char(
        string='Ключ идемпотентности', readonly=True, index=True,
        help='Один ключ — одно распоряжение: повтор с тем же ключом банк '
             'не исполнит дважды.')
    executed_on = fields.Date(string='Списано', readonly=True)

    _one_live = models.UniqueIndex(
        "(share_id) WHERE state IN ('queued', 'bank_review', 'sent', 'unknown')",
        'По доле уже есть выплата в работе.',
    )
    _key_unique = models.UniqueIndex(
        '(idempotency_key)',
        'Ключ идемпотентности повторился.',
    )
    _amount_positive = models.Constraint(
        'CHECK(amount > 0)',
        'Сумма выплаты — больше нуля.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        Share = self.env['coop.nominal.share']
        for vals in vals_list:
            share = Share.browse(vals['share_id'])
            version = self.sudo().search_count([
                ('share_id', '=', share.id), ('kind', '=', vals['kind'])]) + 1
            raw = '%s:%s:%s' % (share.id, vals['kind'], version)
            vals.update({
                'version': version,
                'idempotency_key': hashlib.sha256(raw.encode()).hexdigest(),
                'state': 'bank_review' if share.bank_control else 'queued',
            })
        payouts = super().create(vals_list)
        payouts._check_within_share()
        return payouts

    def _check_within_share(self):
        """Инвариант 3: выплата не больше того, что лежит у её адресата."""
        Entry = self.env['coop.nominal.entry']
        for record in self:
            share = record.share_id
            available = -Entry._leg_sum(
                share.account_id, 'holder', share=share, partner=record.partner_id)
            if share.currency_id.compare_amounts(record.amount, available) > 0:
                raise ValidationError(_(
                    'Выплата %(amount)s больше остатка доли %(code)s у '
                    'получателя: %(available)s.',
                    amount=record.amount, code=share.code, available=available))

    def _mark_executed(self, date):
        """Списание найдено в выписке — выплата исполнена."""
        for record in self:
            if record.state not in LIVE:
                raise UserError(_('Выплата уже закрыта.'))
            record._check_within_share()
            share = record.share_id
            share._post(record.kind, date, [
                {'leg': 'holder', 'amount': record.amount, 'partner': record.partner_id},
                {'leg': 'bank', 'amount': -record.amount},
            ])
            record.write({'state': 'executed', 'executed_on': date})
            share.write({
                'state': 'paid_out' if record.kind == 'payout' else 'refunded',
                'paid_out_on': date,
            })
        return True
