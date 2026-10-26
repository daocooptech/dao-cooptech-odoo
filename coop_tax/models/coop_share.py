# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .ndfl import ndfl

PAID = ('payout', 'return')


class CoopShareMove(models.Model):
    """Выплата и возврат пая — с НДФЛ (решение 513).

    Строк три: сумма, НДФЛ, на руки. Без них пайщик видел «на руки» на
    13–30 % больше, чем получит.

    Налог по проведённому движению застывает: выплата уже ушла, и смена
    настройки или резидентства потом не должна переписывать, сколько
    тогда удержали. Пересчитывается только то, что ещё заявлено.
    """
    _inherit = 'coop.share.move'

    ndfl_base = fields.Monetary(
        string='Облагается', currency_field='currency_id', readonly=True)
    ndfl_amount = fields.Monetary(
        string='НДФЛ', currency_field='currency_id', readonly=True)
    ndfl_rate = fields.Char(string='Ставка', readonly=True)
    net_amount = fields.Monetary(
        string='На руки', currency_field='currency_id', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves.filtered(lambda m: m.kind in PAID)._coop_tax_fill()
        return moves

    def write(self, vals):
        # Застывшее не трогаем: пересчёт — только пока движение не
        # проведено, и в момент проведения.
        open_before = self.filtered(lambda m: m.state != 'confirmed')
        result = super().write(vals)
        if {'amount', 'kind', 'state', 'date'} & set(vals):
            open_before.filtered(lambda m: m.kind in PAID)._coop_tax_fill()
        return result

    def _coop_tax_fill(self):
        for move in self.sorted(lambda m: (m.date, m.id)):
            move.write(move._coop_tax_values())

    def _coop_tax_values(self):
        """НДФЛ с этого движения, если провести его сейчас."""
        self.ensure_one()
        zero = {'ndfl_base': 0, 'ndfl_amount': 0, 'ndfl_rate': False, 'net_amount': 0}
        if self.kind not in PAID or self.amount >= 0 or self.state == 'declined':
            return zero
        gross = -self.amount
        base = self.account_id._coop_taxable(gross, self)
        tax, rate = self.account_id._coop_ndfl(base, self.date, self)
        return {'ndfl_base': base, 'ndfl_amount': tax, 'ndfl_rate': rate or False,
                'net_amount': gross - tax}


class CoopShareAccount(models.Model):
    _inherit = 'coop.share.account'

    ndfl_share_base = fields.Selection(
        related='cooperative_id.coop_ndfl_share_base', string='НДФЛ при возврате пая')
    ndfl_withheld = fields.Monetary(
        string='Удержан НДФЛ', currency_field='currency_id',
        compute='_compute_ndfl_totals', store=True)
    paid_net = fields.Monetary(
        string='Получено на руки', currency_field='currency_id',
        compute='_compute_ndfl_totals', store=True,
        help='Выплаты и возврат пая за вычетом удержанного НДФЛ.')

    # Что будет, если вернуть пай сегодня: экран нужен до заявления, а
    # не после — решение о выходе принимают, глядя на «на руки».
    return_ndfl = fields.Monetary(
        string='НДФЛ при возврате', currency_field='currency_id',
        compute='_compute_return_preview')
    return_net = fields.Monetary(
        string='На руки при возврате', currency_field='currency_id',
        compute='_compute_return_preview')
    return_rate = fields.Char(string='Ставка при возврате', compute='_compute_return_preview')

    @api.depends('move_ids.ndfl_amount', 'move_ids.net_amount', 'move_ids.state',
                 'move_ids.kind', 'paid_out')
    def _compute_ndfl_totals(self):
        for record in self:
            paid = record.move_ids.filtered(
                lambda m: m.state == 'confirmed' and m.kind in PAID)
            record.ndfl_withheld = sum(paid.mapped('ndfl_amount'))
            record.paid_net = record.paid_out - record.ndfl_withheld

    @api.depends('balance', 'cooperative_id.coop_ndfl_share_base',
                 'partner_id.coop_tax_resident', 'partner_id.coop_tax_treaty_rate')
    def _compute_return_preview(self):
        today = fields.Date.context_today(self)
        for record in self:
            if record.balance <= 0:
                record.return_ndfl = record.return_net = 0
                record.return_rate = False
                continue
            base = record._coop_taxable(record.balance)
            tax, rate = record._coop_ndfl(base, today)
            record.return_ndfl = tax
            record.return_net = record.balance - tax
            record.return_rate = rate or False

    def _coop_confirmed_before(self, move=None):
        self.ensure_one()
        moves = self.move_ids.filtered(lambda m: m.state == 'confirmed')
        if move:
            key = (move.date, move.id)
            moves = moves.filtered(lambda m: m != move and (m.date, m.id) < key)
        return moves

    def _coop_taxable(self, gross, move=None):
        """Сколько из выплаты облагается.

        «Со всей суммы» — вся. «Сверх внесённого» — выплата сперва идёт
        из начисленного, внесённое возвращается последним и не облагается:
        внёс 100 000, начислено 30 000, при выходе ещё 5 000 — облагается
        35 000 (разбор бухгалтера 26.10, У1).
        """
        self.ensure_one()
        if self.cooperative_id.coop_ndfl_share_base != 'excess':
            return gross
        before = self._coop_confirmed_before(move)
        balance = sum(before.filtered(lambda m: m.kind != 'entry').mapped('amount'))
        contributed = sum(before.filtered(
            lambda m: m.kind in ('share', 'extra', 'in_kind')).mapped('amount'))
        paid = before.filtered(lambda m: m.kind in PAID)
        untaxed_paid = sum(-m.amount - m.ndfl_base for m in paid)
        remaining = max(0.0, contributed - untaxed_paid)
        return min(gross, max(0.0, balance - remaining))

    def _coop_ndfl(self, base, date, move=None):
        """Налог с базы по ставке пайщика и по шкале за год у этого агента."""
        self.ensure_one()
        partner = self.partner_id
        year = (date or fields.Date.context_today(self)).year
        earlier = self.env['coop.share.move'].search([
            ('account_id.partner_id', '=', partner.id),
            ('account_id.cooperative_id', '=', self.cooperative_id.id),
            ('kind', 'in', PAID), ('state', '=', 'confirmed'),
            ('date', '>=', '%d-01-01' % year), ('date', '<=', '%d-12-31' % year),
        ]).filtered(lambda m: not move or (m != move and (m.date, m.id) < (move.date, move.id)))
        return ndfl(base, sum(earlier.mapped('ndfl_base')),
                    resident=partner.coop_tax_resident,
                    treaty_rate=partner.coop_tax_treaty_rate)
