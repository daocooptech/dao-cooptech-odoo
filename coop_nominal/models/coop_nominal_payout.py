# -*- coding: utf-8 -*-
import hashlib

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Выплата «живая», пока может дойти до банка или уже ушла и ответа нет.
LIVE = ('queued', 'bank_review', 'sent', 'unknown')


class CoopNominalPayout(models.Model):
    """Распоряжение выплатить удержанное получателю или вернуть плательщику.

    Выплата исполнена, только когда списание видно в выписке: ответ банка
    «принято» — ещё не деньги у получателя. На удержание — одна живая выплата,
    иначе повтор после сбоя заплатил бы дважды.

    Возврат нераспознанного поступления — тоже выплата, но без удержания:
    источник у неё строка выписки, а получатель — тот, кто прислал деньги,
    по реквизитам из этой строки.
    """
    _name = 'coop.nominal.payout'
    _description = 'Выплата с номинального счёта'
    _inherit = ['mail.thread']
    _order = 'id desc'

    hold_id = fields.Many2one(
        'coop.nominal.hold', string='Удержание',
        ondelete='restrict', index=True)
    source_line_id = fields.Many2one(
        'coop.nominal.statement.line', string='Возврат строки выписки',
        ondelete='restrict', index=True,
        help='Нераспознанное поступление, которое возвращаем отправителю.')
    account_id = fields.Many2one(
        'coop.nominal.account', string='Счёт', compute='_compute_account_id',
        store=True, index=True)
    kind = fields.Selection([
        ('payout', 'Выплата получателю'),
        ('refund', 'Возврат плательщику'),
    ], string='Вид', required=True)
    partner_id = fields.Many2one('res.partner', string='Кому', index=True)
    # Реквизиты снимком на момент распоряжения: по ним уходит платёжка, и
    # смена реквизитов в карточке не должна менять уже поставленную.
    recipient_name = fields.Char(string='Получатель', readonly=True)
    recipient_inn = fields.Char(string='ИНН получателя', readonly=True)
    recipient_kpp = fields.Char(string='КПП получателя', readonly=True)
    recipient_account = fields.Char(string='Счёт получателя', readonly=True)
    recipient_bic = fields.Char(string='БИК банка получателя', readonly=True)
    amount = fields.Monetary(
        string='Сумма', currency_field='currency_id', required=True)
    currency_id = fields.Many2one(related='account_id.currency_id')
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
        "(hold_id) WHERE state IN ('queued', 'bank_review', 'sent', 'unknown')",
        'По удержанию уже есть выплата в работе.',
    )
    _one_live_line = models.UniqueIndex(
        "(source_line_id) WHERE state IN ('queued', 'bank_review', 'sent', 'unknown')",
        'По строке выписки уже есть возврат в работе.',
    )
    _one_source = models.Constraint(
        'CHECK((hold_id IS NULL) != (source_line_id IS NULL))',
        'У выплаты один источник: удержание или строка выписки.',
    )
    _hold_has_partner = models.Constraint(
        'CHECK(hold_id IS NULL OR partner_id IS NOT NULL)',
        'Выплата по удержанию идёт стороне сделки.',
    )
    _key_unique = models.UniqueIndex(
        '(idempotency_key)',
        'Ключ идемпотентности повторился.',
    )
    _amount_positive = models.Constraint(
        'CHECK(amount > 0)',
        'Сумма выплаты — больше нуля.',
    )

    @api.depends('hold_id.account_id', 'source_line_id.account_id')
    def _compute_account_id(self):
        for record in self:
            record.account_id = record.hold_id.account_id or record.source_line_id.account_id

    @api.model_create_multi
    def create(self, vals_list):
        Hold = self.env['coop.nominal.hold']
        Line = self.env['coop.nominal.statement.line']
        today = fields.Date.context_today(self)
        for vals in vals_list:
            hold = Hold.browse(vals.get('hold_id'))
            line = Line.browse(vals.get('source_line_id'))
            source, source_field = (hold, 'hold_id') if hold else (line, 'source_line_id')
            version = self.sudo().search_count([
                (source_field, '=', source.id), ('kind', '=', vals['kind'])]) + 1
            raw = '%s:%s:%s' % (source.id, vals['kind'], version)
            if line:
                raw = 'line:' + raw
                bank_control = line.account_id._setting_on(today).bank_control
                vals.update({
                    'recipient_name': line.partner_name,
                    'recipient_inn': line.partner_inn,
                    'recipient_kpp': line.partner_kpp,
                    'recipient_account': line.partner_account,
                    'recipient_bic': line.partner_bic,
                })
            else:
                bank_control = hold.bank_control
                partner = self.env['res.partner'].browse(vals.get('partner_id'))
                bank = partner.bank_ids[:1]
                vals.update({
                    'recipient_name': partner.name,
                    'recipient_inn': partner.vat,
                    'recipient_kpp': partner.kpp if 'kpp' in partner._fields else False,
                    'recipient_account': bank.account_number,
                    'recipient_bic': bank.bank_bic,
                })
            vals.update({
                'version': version,
                'idempotency_key': hashlib.sha256(raw.encode()).hexdigest(),
                'state': 'bank_review' if bank_control else 'queued',
            })
        payouts = super().create(vals_list)
        payouts._check_within_hold()
        return payouts

    def _available(self):
        """Сколько можно выплатить по источнику этой выплаты её адресату."""
        self.ensure_one()
        line = self.source_line_id
        if line:
            open_line = line.state == 'unrecognized' and line.direction == 'in'
            return line.amount if open_line else 0.0
        return -self.env['coop.nominal.entry']._leg_sum(
            self.hold_id.account_id, 'holder', hold=self.hold_id, partner=self.partner_id)

    def _check_within_hold(self):
        """Инвариант 3: выплата не больше того, что лежит у её адресата."""
        for record in self:
            available = record._available()
            if record.currency_id.compare_amounts(record.amount, available) > 0:
                raise ValidationError(_(
                    'Выплата %(amount)s больше того, что можно выплатить по '
                    '%(source)s: %(available)s.',
                    amount=record.amount,
                    source=record.hold_id.code or record.source_line_id.display_name,
                    available=available))

    def _mark_executed(self, date, statement_line=None, from_unrecognized=False):
        """Списание найдено в выписке — выплата исполнена.

        `from_unrecognized` — списание сперва легло в нераспознанное, и его
        разобрали руками позже: деньги со счёта второй раз не списываем, а
        переносим запись из нераспознанного.
        """
        Entry = self.env['coop.nominal.entry']
        for record in self:
            if record.state not in LIVE:
                raise UserError(_('Выплата уже закрыта.'))
            record._check_within_hold()
            line = record.source_line_id
            if line:
                # Возврат нераспознанного: поступление и списание гасят друг
                # друга в нераспознанном. Если и списание сперва ушло туда,
                # проводить уже нечего.
                if not from_unrecognized:
                    Entry._post(record.account_id, 'refund', date, [
                        {'leg': 'unrecognized', 'amount': record.amount},
                        {'leg': 'bank', 'amount': -record.amount},
                    ], statement_line=statement_line)
                record.write({'state': 'executed', 'executed_on': date})
                line._mark_resolved('refund')
                continue
            hold = record.hold_id
            post_on = fields.Date.context_today(record) if from_unrecognized else date
            hold._post(record.kind, post_on, [
                {'leg': 'holder', 'amount': record.amount, 'partner': record.partner_id},
                {'leg': 'unrecognized' if from_unrecognized else 'bank',
                 'amount': -record.amount},
            ], statement_line=statement_line)
            record.write({'state': 'executed', 'executed_on': date})
            hold.write({
                'state': 'paid_out' if record.kind == 'payout' else 'refunded',
                'paid_out_on': date,
            })
        return True
