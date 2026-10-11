# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Состояния, в которых деньги удержания лежат на счёте и их можно заморозить.
HELD = ('held_buyer', 'held_seller', 'payout_queued', 'refund_queued')


class CoopNominalHold(models.Model):
    """Платёж на удержании — позиция графика оплат на номинальном счёте.

    Не путать с долями в проектах и на биржах: здесь только деньги
    одного платежа, которые лежат до акта.

    Путь удержания: ждёт оплаты → пришла, бенефициар покупатель → (акт)
    бенефициар продавец → выплата в очереди → выплачена. Возврат —
    от покупателя-бенефициара в очередь возврата и обратно покупателю.
    При споре удержание замораживается и помнит, откуда.

    Если по настройкам бенефициар один продавец, шага «бенефициар
    покупатель» нет, а вернуть деньги покупателю можно только с согласия
    продавца: деньги уже его.
    """
    _name = 'coop.nominal.hold'
    _description = 'Платёж на удержании'
    _inherit = ['mail.thread']
    _order = 'id desc'

    code = fields.Char(
        string='Код', compute='_compute_code',
        help='Код для назначения платежа: по нему выписка находит удержание.')
    account_id = fields.Many2one(
        'coop.nominal.account', string='Счёт', required=True,
        ondelete='restrict', index=True)
    payment_id = fields.Many2one(
        'coop.deal.payment', string='Позиция графика', required=True,
        ondelete='restrict', index=True)
    deal_id = fields.Many2one(
        related='payment_id.deal_id', store=True, index=True, string='Сделка')
    payer_id = fields.Many2one(
        'res.partner', string='Плательщик', required=True, index=True)
    payee_id = fields.Many2one(
        'res.partner', string='Получатель', required=True, index=True)
    beneficiary_id = fields.Many2one(
        'res.partner', string='Бенефициар сейчас', readonly=True,
        tracking=True)
    amount = fields.Monetary(
        string='Сумма', currency_field='currency_id', required=True)
    fee_amount = fields.Monetary(
        string='Комиссия', currency_field='currency_id', readonly=True)
    vat_amount = fields.Monetary(
        string='НДС в комиссии', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one(related='account_id.currency_id')

    # Снимок настроек на момент создания: следующая версия настроек
    # удержание не трогает.
    setting_id = fields.Many2one(
        'coop.nominal.setting', string='Версия настроек', readonly=True,
        ondelete='restrict')
    beneficiary_mode = fields.Selection(
        [('both', 'Обе стороны'), ('seller', 'Только продавец')],
        string='Бенефициары', readonly=True)
    fee_mode = fields.Selection(
        [('withhold', 'Удержать из платежа'), ('invoice', 'Выставить счёт')],
        string='Порядок комиссии', readonly=True)
    books_mode = fields.Selection(
        [('off_balance', 'За балансом'), ('on_balance', 'На балансе')],
        string='Учёт у оператора', readonly=True)
    bank_control = fields.Boolean(string='Контроль банка', readonly=True)

    # Три даты, и все по выписке: «отправили распоряжение» — не то же,
    # что «деньги списаны».
    credited_on = fields.Date(string='Зачислено', readonly=True)
    act_on = fields.Date(string='Акт', readonly=True)
    paid_out_on = fields.Date(string='Списано получателю', readonly=True)

    state = fields.Selection([
        ('awaiting', 'Ждёт оплаты'),
        ('held_buyer', 'Лежит, бенефициар покупатель'),
        ('held_seller', 'Лежит, бенефициар продавец'),
        ('payout_queued', 'Выплата в очереди'),
        ('paid_out', 'Выплачено'),
        ('refund_queued', 'Возврат в очереди'),
        ('refunded', 'Возвращено'),
        ('frozen', 'Заморожено спором'),
        ('cancelled', 'Отменено до оплаты'),
    ], string='Состояние', default='awaiting', required=True, index=True,
        readonly=True, tracking=True)
    frozen_from = fields.Char(string='Заморожено из', readonly=True)
    refund_consent = fields.Boolean(string='Продавец согласен на возврат', readonly=True)
    refund_consent_by_id = fields.Many2one(
        'res.users', string='Согласие дал', readonly=True)

    entry_ids = fields.One2many(
        'coop.nominal.entry', 'hold_id', string='Книга')
    payout_ids = fields.One2many(
        'coop.nominal.payout', 'hold_id', string='Выплаты')
    held_amount = fields.Monetary(
        string='Лежит на счёте', currency_field='currency_id',
        compute='_compute_held_amount')

    _payment_unique = models.Constraint(
        'unique(payment_id)',
        'На позицию графика — одно удержание.',
    )
    _amount_positive = models.Constraint(
        'CHECK(amount > 0)',
        'Сумма удержания — больше нуля.',
    )

    _rec_names_search = ['deal_id.name', 'payer_id.name', 'payee_id.name']

    def _compute_code(self):
        for record in self:
            record.code = 'CT-%s' % record.id if record.id else False

    @api.depends('deal_id.name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = ' · '.join(filter(None, [record.code, record.deal_id.name]))

    @api.model
    def _search_display_name(self, operator, value):
        # Администратор ищет удержание так, как оно написано в назначении
        # платежа: «CT-15».
        match = isinstance(value, str) and re.fullmatch(
            r'\s*[CС][TТ]\s*-?\s*(\d+)\s*', value, re.IGNORECASE)
        if match and operator in ('ilike', '='):
            return [('id', '=', int(match.group(1)))]
        return super()._search_display_name(operator, value)

    @api.depends('entry_ids.amount')
    def _compute_held_amount(self):
        Entry = self.env['coop.nominal.entry']
        for record in self:
            record.held_amount = -Entry._leg_sum(
                record.account_id, 'holder', hold=record) if record.id else 0.0

    @api.constrains('payer_id', 'payee_id', 'payment_id', 'account_id')
    def _check_parties(self):
        for record in self:
            if record.payer_id == record.payee_id:
                raise ValidationError(_('Плательщик и получатель удержания — разные стороны.'))
            if record.payment_id.currency_id != record.account_id.currency_id:
                raise ValidationError(_(
                    'Безопасная сделка принимает платёж только в валюте счёта хранения.'))

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)
        Account = self.env['coop.nominal.account']
        for vals in vals_list:
            account = Account.browse(vals['account_id'])
            setting = account._setting_on(today)
            currency = account.currency_id
            fee = currency.round(vals.get('amount', 0.0) * setting.fee_percent / 100)
            vat = currency.round(
                fee * setting.fee_vat_percent / (100 + setting.fee_vat_percent))
            vals.update({
                'setting_id': setting.id,
                'beneficiary_mode': setting.beneficiary_mode,
                'fee_mode': setting.fee_mode,
                'books_mode': setting.books_mode,
                'bank_control': setting.bank_control,
                'fee_amount': fee,
                'vat_amount': vat,
                'state': 'awaiting',
            })
        return super().create(vals_list)

    # Сумма, условия и стороны удержания — часть договорённости. После создания
    # их меняют новым удержанием, а не правкой.
    _FROZEN_FIELDS = {'account_id', 'payment_id', 'payer_id', 'payee_id', 'amount',
                      'setting_id', 'beneficiary_mode', 'fee_mode', 'books_mode',
                      'bank_control', 'fee_amount', 'vat_amount'}

    def write(self, vals):
        if self._FROZEN_FIELDS & set(vals):
            raise UserError(_(
                'Сумма, стороны и условия удержания не меняются после создания.'))
        return super().write(vals)

    def _expect(self, *states):
        for record in self:
            if record.state not in states:
                raise UserError(_(
                    'Удержание %(code)s в состоянии «%(state)s» — это действие '
                    'для неё недоступно.',
                    code=record.code,
                    state=dict(record._fields['state'].selection)[record.state]))

    def _post(self, kind, date, lines, statement_line=None):
        self.ensure_one()
        for line in lines:
            line.setdefault('hold', self)
        return self.env['coop.nominal.entry']._post(
            self.account_id, kind, date, lines, statement_line=statement_line)

    def _credit(self, date, statement_line=None, from_unrecognized=False):
        """Деньги плательщика пришли на счёт — по выписке.

        Совпавшая строка выписки ставит позицию графика оплаченной: это
        сильнее, чем «я получил» от стороны.

        `from_unrecognized` — деньги уже лежат в нераспознанном, их опознали
        руками: переносим их бенефициару сегодняшней проводкой (книга о
        прошлом не переписывается), а зачисленными считаем с даты выписки.
        """
        self._expect('awaiting')
        for record in self:
            first = record.payer_id if record.beneficiary_mode == 'both' else record.payee_id
            if from_unrecognized:
                kind, leg, post_on = 'recognize', 'unrecognized', fields.Date.context_today(record)
            else:
                kind, leg, post_on = 'credit', 'bank', date
            record._post(kind, post_on, [
                {'leg': leg, 'amount': record.amount},
                {'leg': 'holder', 'amount': -record.amount, 'partner': first},
            ], statement_line=statement_line)
            record.write({
                'state': 'held_buyer' if record.beneficiary_mode == 'both' else 'held_seller',
                'beneficiary_id': first.id,
                'credited_on': date,
            })
            record.payment_id.sudo().write({'state': 'paid', 'paid_on': date})
        return True

    def _act(self, date):
        """Акт подписан: деньги переходят продавцу, оператор берёт комиссию."""
        self._expect('held_buyer', 'held_seller')
        for record in self:
            if record.state == 'held_buyer':
                record._post('beneficiary', date, [
                    {'leg': 'holder', 'amount': record.amount, 'partner': record.payer_id},
                    {'leg': 'holder', 'amount': -record.amount, 'partner': record.payee_id},
                ])
            if record.fee_mode == 'withhold' and not record.currency_id.is_zero(record.fee_amount):
                record._post('fee', date, [
                    {'leg': 'holder', 'amount': record.fee_amount, 'partner': record.payee_id},
                    {'leg': 'fee', 'amount': -record.fee_amount},
                ])
            record.write({
                'state': 'held_seller',
                'beneficiary_id': record.payee_id.id,
                'act_on': date,
            })
        return True

    def _freeze(self):
        """Спор: деньги остаются на месте, пока его не разберут.

        Выплату, ещё не отправленную в банк, снимаем с очереди;
        отправленную остановить нельзя — её удержание не трогаем.
        """
        for record in self.filtered(lambda r: r.state in HELD):
            # Отданная в банк (файлом или подключением) уже там, даже если
            # банк ещё проверяет основание.
            live = record.payout_ids.filtered(
                lambda p: p.state in ('queued', 'bank_review') and not p._in_bank())
            if record.state in ('payout_queued', 'refund_queued') and not live:
                continue
            live.write({'state': 'cancelled'})
            back = {'payout_queued': 'held_seller', 'refund_queued': 'held_buyer'}
            record.write({
                'state': 'frozen',
                'frozen_from': back.get(record.state, record.state),
            })
        return True

    def _unfreeze(self):
        """Спор закрыт: удержание возвращается туда, где была.

        Деление суммы по решению спора — отдельное действие, оно ещё не
        решено владельцем.
        """
        self._expect('frozen')
        for record in self:
            record.write({'state': record.frozen_from, 'frozen_from': False})
        return True

    def _queue_payout(self):
        self._expect('held_seller')
        for record in self:
            record.account_id._check_payouts_allowed()
            amount = -self.env['coop.nominal.entry']._leg_sum(
                record.account_id, 'holder', hold=record, partner=record.payee_id)
            self.env['coop.nominal.payout'].create({
                'hold_id': record.id,
                'kind': 'payout',
                'partner_id': record.payee_id.id,
                'amount': amount,
            })
            record.state = 'payout_queued'
        return True

    def _queue_refund(self):
        self._expect('held_buyer', 'held_seller')
        for record in self:
            if record.state == 'held_seller':
                if record.beneficiary_mode != 'seller' or record.act_on:
                    raise UserError(_(
                        'Деньги удержания %s уже принадлежат продавцу по акту: '
                        'вернуть их можно только новой сделкой.') % record.code)
                if not record.refund_consent:
                    raise UserError(_(
                        'Деньги удержания %s принадлежат продавцу: возврат — только '
                        'с его согласия.') % record.code)
            record.account_id._check_payouts_allowed()
            if record.state == 'held_seller':
                # Продавец согласился — деньги снова покупателя.
                record._post('beneficiary', fields.Date.context_today(record), [
                    {'leg': 'holder', 'amount': record.amount, 'partner': record.payee_id},
                    {'leg': 'holder', 'amount': -record.amount, 'partner': record.payer_id},
                ])
                record.beneficiary_id = record.payer_id
            self.env['coop.nominal.payout'].create({
                'hold_id': record.id,
                'kind': 'refund',
                'partner_id': record.payer_id.id,
                'amount': record.held_amount,
            })
            record.state = 'refund_queued'
        return True

    def _cancel(self):
        """Сделку отменили до оплаты — держать нечего."""
        self._expect('awaiting')
        self.write({'state': 'cancelled'})
        return True

    def action_consent_refund(self):
        """Согласие продавца вернуть деньги покупателю.

        Даёт только получатель платежа: деньги его, и решать ему.
        """
        for record in self:
            if record.payee_id not in self.env.user.coop_treasury_partner_ids:
                raise UserError(_(
                    'Согласие на возврат даёт получатель платежа.'))
            record.sudo().write({
                'refund_consent': True,
                'refund_consent_by_id': self.env.user.id,
            })
        return True
