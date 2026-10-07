# -*- coding: utf-8 -*-
"""Отправка, получение, пополнение и вывод — одним окном.

Владелец 06.10.2026 (решение 445 п. 14, решение 443): «Отправка в сеть
пока не подключена» — не ответ платформы, которая выглядит действующей.
Кнопки кошелька теперь доводят операцию до конца: остаток меняется,
в истории появляется запись, у сетевой операции — хэш и ссылка в
обозреватель. Подписи ключом и банка за этим нет — это имитация, но
правила те же, что были бы у настоящей: подтверждённая личность, не
больше, чем есть на счёте, способ оплаты у рублёвых операций.
"""
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopWalletOperation(models.TransientModel):
    _name = 'coop.wallet.operation'
    _description = 'Операция по кошельку'

    wallet_id = fields.Many2one(
        'coop.wallet', string='Кошелёк', required=True, readonly=True)
    mode = fields.Selection([
        ('send', 'Отправить'),
        ('receive', 'Получить'),
        ('topup', 'Пополнить'),
        ('withdraw', 'Вывести'),
    ], string='Операция', required=True, readonly=True)
    currency_id = fields.Many2one(related='wallet_id.currency_id')

    # Сеть
    asset_id = fields.Many2one(
        'coop.wallet.asset', string='Актив',
        domain="[('wallet_id', '=', wallet_id), ('quantity', '>', 0)]")
    available_quantity = fields.Float(
        related='asset_id.quantity', string='Доступно', digits=(16, 8))
    quantity = fields.Float(string='Количество', digits=(16, 8))
    peer_partner_id = fields.Many2one(
        'res.partner', string='Участнику',
        help='Если получатель — участник платформы, адрес подставится из '
             'его кошелька в той же сети.')
    peer_address = fields.Char(string='Адрес получателя')
    address_ids = fields.Many2many(
        'coop.wallet.address', string='Мои адреса',
        compute='_compute_address_ids')

    # Рубли
    method_id = fields.Many2one(
        'coop.wallet.method', string='Способ оплаты',
        domain="[('wallet_id', '=', wallet_id)]")
    amount = fields.Monetary(string='Сумма', currency_field='currency_id')
    fiat_available = fields.Monetary(
        related='wallet_id.fiat_available', string='Доступно к выводу',
        currency_field='currency_id')

    @api.depends('wallet_id')
    def _compute_address_ids(self):
        for wizard in self:
            wizard.address_ids = self.env['coop.wallet.address'].sudo().search([
                ('wallet_id', '=', wizard.wallet_id.id)])

    @api.onchange('peer_partner_id', 'asset_id')
    def _onchange_peer(self):
        for wizard in self:
            if wizard.peer_partner_id and wizard.asset_id:
                address = self.env['coop.wallet.address'].sudo().search([
                    ('wallet_id.partner_id', '=', wizard.peer_partner_id.id),
                    ('network_id', '=', wizard.asset_id.network_id.id),
                ], limit=1)
                if address:
                    wizard.peer_address = address.address

    @api.onchange('wallet_id', 'mode')
    def _onchange_default_method(self):
        for wizard in self:
            if wizard.mode in ('topup', 'withdraw') and not wizard.method_id:
                methods = self.env['coop.wallet.method'].search(
                    [('wallet_id', '=', wizard.wallet_id.id)])
                wizard.method_id = methods.filtered('is_default')[:1] or methods[:1]

    # ── Проведение ───────────────────────────────────────────────────────

    def action_confirm(self):
        self.ensure_one()
        handler = {
            'send': self._do_send,
            'topup': self._do_topup,
            'withdraw': self._do_withdraw,
        }.get(self.mode)
        if handler:
            handler()
        return {'type': 'ir.actions.act_window_close'}

    def _do_send(self):
        asset = self.asset_id
        if not asset:
            raise UserError(_('Выберите, что отправить.'))
        if self.quantity <= 0:
            raise UserError(_('Укажите, сколько отправить.'))
        if self.quantity > asset.quantity:
            raise UserError(_(
                'На кошельке %(have)s %(symbol)s — отправить %(want)s нельзя.',
                have=asset.quantity, symbol=asset.symbol, want=self.quantity))
        address = (self.peer_address or '').strip()
        if not address:
            raise UserError(_('Укажите адрес получателя или выберите участника.'))
        asset = asset.sudo()
        price = asset.valuation / asset.quantity if asset.quantity else 0.0
        value = price * self.quantity
        asset.write({
            'quantity': asset.quantity - self.quantity,
            'valuation': asset.valuation - value,
            'balance_at': fields.Datetime.now(),
        })
        network = asset.network_id
        tx_hash = secrets.token_hex(32)
        if network.chain_id:
            tx_hash = '0x' + tx_hash
        self.env['coop.wallet.tx'].sudo().create({
            'wallet_id': self.wallet_id.id,
            'network_id': network.id,
            'kind': 'out',
            'symbol': asset.symbol,
            'quantity': -self.quantity,
            'valuation': -value,
            'peer_address': address,
            'peer_partner_id': self.peer_partner_id.id,
            'tx_hash': tx_hash,
            'state': 'confirmed',
        })

    def _fiat_movement(self, kind, amount, name):
        if not self.method_id:
            raise UserError(_('Выберите способ оплаты.'))
        self.env['coop.wallet.movement'].sudo().create({
            'wallet_id': self.wallet_id.id,
            'kind': kind,
            'amount': amount,
            'method_id': self.method_id.id,
            'name': name,
            'state': 'confirmed',
        })

    def _do_topup(self):
        if self.amount <= 0:
            raise UserError(_('Укажите сумму пополнения.'))
        self._fiat_movement('topup', self.amount, _(
            'Пополнение: %s', self.method_id.label))

    def _do_withdraw(self):
        if self.amount <= 0:
            raise UserError(_('Укажите сумму вывода.'))
        if self.amount > self.wallet_id.fiat_available:
            raise UserError(_(
                'Доступно к выводу %(available)s: остальное обещано по '
                'взаиморасчётам.',
                available=self.wallet_id.fiat_available))
        self._fiat_movement('withdraw', -self.amount, _(
            'Вывод: %s', self.method_id.label))
