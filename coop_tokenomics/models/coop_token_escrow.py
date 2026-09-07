# -*- coding: utf-8 -*-
"""Эскроу: деньги покупателя ждут поставки.

Обещание поставить товар к сроку стоит ровно столько, сколько стоит
возможность вернуть деньги, если товар не привезли. Поэтому оплата не
уходит поставщику сразу: она лежит до приёмки, а по истечении срока
возвращается покупателю сама — без заявления, разбирательства и просьб.

Три состояния и ничего лишнего:

- **лежит** — покупатель заплатил, поставщик ещё не привёз;
- **отдано** — обе стороны подтвердили поставку, деньги ушли поставщику;
- **возвращено** — срок прошёл, деньги вернулись покупателю.

Спор — не состояние эскроу, а причина задержать возврат: пока стороны
разбираются, деньги остаются на месте. Это единственная развилка, где
платформа вмешивается, и она видна отдельным признаком.

**Чем это пока является.** Расчёт ведётся в рублях, а рублёвого токена в
сети TON нет: значит блокировка — учётная запись, а не смарт-контракт.
Правила при этом те же, что заложены в контракт: сроки, автовозврат,
двусторонняя приёмка. Когда появится ончейн-расчёт, у записи добавится
адрес контракта, а поведение останется прежним — иначе участники,
привыкшие к одному порядку, столкнутся с другим.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopTokenEscrow(models.Model):
    _name = 'coop.token.escrow'
    _description = 'Эскроу по сделке с токенами'
    _order = 'due_date, id desc'
    _rec_name = 'display_name'

    display_name = fields.Char(compute='_compute_display_name', store=True)

    trade_id = fields.Many2one(
        'coop.token.trade', string='Сделка', required=True, index=True,
        ondelete='cascade')
    claim_id = fields.Many2one(
        'coop.token.claim', related='trade_id.claim_id', store=True, index=True)
    buyer_id = fields.Many2one(
        'res.partner', string='Покупатель', required=True, index=True)
    seller_id = fields.Many2one(
        'res.partner', string='Поставщик', required=True, index=True)

    amount = fields.Float(
        string='Сумма', required=True, digits=(16, 2),
        help='Оплата покупателя, лежащая до поставки.')
    quantity = fields.Float(
        string='Количество', required=True, digits=(16, 3))
    due_date = fields.Date(
        string='Срок поставки', required=True, index=True,
        help='После этого дня покупатель вправе забрать деньги.')

    state = fields.Selection([
        ('held', 'Лежит до поставки'),
        ('released', 'Отдано поставщику'),
        ('refunded', 'Возвращено покупателю'),
    ], string='Состояние', default='held', required=True, index=True)

    # Приёмка двусторонняя: одной подписи мало.
    #
    # Подтверждение только поставщика означало бы, что он сам решает,
    # когда получить деньги. Подтверждение только покупателя — что он
    # может тянуть с приёмкой, держа чужие деньги. Поэтому нужны обе, а
    # молчание одной из сторон разрешается сроком.
    delivered_on = fields.Datetime(
        string='Поставщик отметил поставку', readonly=True)
    accepted_on = fields.Datetime(
        string='Покупатель принял', readonly=True)
    settled_on = fields.Datetime(string='Расчёт завершён', readonly=True)

    disputed = fields.Boolean(
        string='Спор',
        help='Пока стороны разбираются, деньги остаются на месте: '
             'автовозврат по сроку не срабатывает.')
    dispute_note = fields.Text(string='Суть спора')

    days_left = fields.Integer(
        string='Дней до срока', compute='_compute_days_left')

    @api.depends('claim_id.display_name', 'buyer_id.name', 'amount')
    def _compute_display_name(self):
        for record in self:
            record.display_name = _('%(claim)s — %(buyer)s') % {
                'claim': record.claim_id.display_name or _('выпуск'),
                'buyer': record.buyer_id.name or _('покупатель'),
            }

    @api.depends('due_date')
    def _compute_days_left(self):
        today = fields.Date.context_today(self)
        for record in self:
            record.days_left = (record.due_date - today).days if record.due_date else 0

    # ── Приёмка ──────────────────────────────────────────────────────────

    def action_mark_delivered(self):
        """Поставщик отмечает, что привёз."""
        for record in self:
            record._check_party(record.seller_id, _('отметить поставку'))
            if record.state != 'held':
                raise UserError(_('Расчёт по этой сделке уже завершён.'))
            record.delivered_on = fields.Datetime.now()
            record._settle_if_both()
        return True

    def action_accept(self):
        """Покупатель подтверждает, что принял товар."""
        for record in self:
            record._check_party(record.buyer_id, _('принять поставку'))
            if record.state != 'held':
                raise UserError(_('Расчёт по этой сделке уже завершён.'))
            record.accepted_on = fields.Datetime.now()
            record._settle_if_both()
        return True

    def _settle_if_both(self):
        """Отдать деньги поставщику, когда подтвердили обе стороны."""
        for record in self:
            if record.delivered_on and record.accepted_on:
                record.write({
                    'state': 'released',
                    'settled_on': fields.Datetime.now(),
                    'disputed': False,
                })
                record.claim_id._escrow_released()

    def action_dispute(self, note=None):
        """Заявить спор — деньги остаются на месте до разбора."""
        for record in self:
            record._check_party(record.buyer_id | record.seller_id,
                                _('заявить спор'))
            if record.state != 'held':
                raise UserError(_(
                    'Спорить не о чем: расчёт по сделке уже завершён.'))
            record.write({'disputed': True, 'dispute_note': note or record.dispute_note})
        return True

    def action_refund(self):
        """Вернуть деньги покупателю.

        Возврат доступен после срока — и только тогда. До срока поставщик
        вправе привезти товар, и досрочный возврат означал бы, что
        покупатель может передумать за чужой счёт.
        """
        today = fields.Date.context_today(self)
        for record in self:
            if record.state != 'held':
                raise UserError(_('Деньги по этой сделке уже не лежат.'))
            if record.due_date >= today:
                raise UserError(_(
                    'Срок поставки ещё не прошёл — до %(date)s поставщик '
                    'вправе привезти товар.', date=record.due_date))
            record.write({
                'state': 'refunded',
                'settled_on': fields.Datetime.now(),
            })
            record.claim_id._escrow_refunded()
        return True

    def _check_party(self, allowed, action):
        """Действие доступно только стороне сделки."""
        self.ensure_one()
        me = self.env.user._coop_acting_partner()
        if me not in allowed and not self.env.user.has_group('base.group_system'):
            raise UserError(_(
                'Только сторона сделки может %(action)s.', action=action))

    # ── Автовозврат ──────────────────────────────────────────────────────

    @api.model
    def _cron_refund_overdue(self):
        """Вернуть деньги по сделкам, где срок прошёл.

        Раз в сутки, а не мгновенно в полночь: поставка, привезённая в
        последний день, должна успеть получить подтверждение покупателя.
        Спорные не трогаем — там уже разбираются люди.
        """
        today = fields.Date.context_today(self)
        overdue = self.search([
            ('state', '=', 'held'),
            ('disputed', '=', False),
            ('due_date', '<', today),
        ])
        for record in overdue:
            record.write({
                'state': 'refunded',
                'settled_on': fields.Datetime.now(),
            })
            record.claim_id._escrow_refunded()
        if overdue:
            self.env['ir.logging'].sudo().create({
                'name': 'coop.token.escrow',
                'type': 'server',
                'level': 'INFO',
                'dbname': self.env.cr.dbname,
                'message': 'Автовозврат по сроку: %s сделок' % len(overdue),
                'path': 'coop_tokenomics',
                'func': '_cron_refund_overdue',
                'line': '0',
            })
        return len(overdue)
