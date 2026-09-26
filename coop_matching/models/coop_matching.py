# -*- coding: utf-8 -*-
"""Движок сведения заявок — общий для «Токеномики» и «DEX биржи».

Решение 417. Правило исполнения — цена-время: встречная заявка с лучшей
ценой исполняется первой, при равной цене — выставленная раньше. Цена
сделки — цена заявки, стоявшей в стакане: кто пришёл вторым, берёт по
цене первого (как на любой бирже).

Рыночная заявка исполняется по всему, что есть в стакане, и остаток не
ставит — снимается сразу. Своя встречная заявка пропускается: торговать
с собой нельзя.
"""
import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

OPEN_STATES = ('open', 'partial')


def canonical(obj):
    """Каноническая запись тела — как в протоколе обмена узлов: ключи по
    порядку, без пробелов, без дробных чисел (числа строками)."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def num(value, digits=6):
    text = ('%.*f' % (digits, value or 0)).rstrip('0').rstrip('.')
    return text or '0'


class CoopMatchingMixin(models.AbstractModel):
    """Заявка, которую можно сводить.

    Модель, подключившая примесь, объявляет:

    - поля `side` ('buy'/'sell'), `state` (с 'open', 'partial', 'done',
      'cancelled'), `partner_id`, количество-остаток `quantity_left` и
      поле цены — его имя в `_coop_price_field`;
    - `_coop_market_domain()` — какие заявки с ней на одном рынке;
    - `_coop_market_key()` — имя рынка для журнала;
    - `_coop_on_fill(maker, quantity, price)` — что сделать с исполнением:
      обычно завести сделку, которую потом подписывают стороны.
    """
    _name = 'coop.matching.mixin'
    _description = 'Сводимая заявка'
    _coop_price_field = 'price'

    order_type = fields.Selection([
        ('limit', 'Лимитная'),
        ('market', 'По рынку'),
    ], string='Тип заявки', default='limit', required=True,
        help='Лимитная ждёт в стакане своей цены. По рынку — исполняется '
             'сразу по лучшим встречным ценам, остаток снимается.')

    # ── Что объявляет модель ─────────────────────────────────────────

    def _coop_market_domain(self):
        raise NotImplementedError

    def _coop_market_key(self):
        raise NotImplementedError

    def _coop_on_fill(self, maker, quantity, price):
        raise NotImplementedError

    # ── Сведение ─────────────────────────────────────────────────────

    def _coop_price(self):
        return self[self._coop_price_field] or 0.0

    def _coop_opposite(self):
        """Встречные заявки в порядке исполнения, под блокировкой строк."""
        self.ensure_one()
        opposite = 'sell' if self.side == 'buy' else 'buy'
        domain = list(self._coop_market_domain()) + [
            ('side', '=', opposite),
            ('state', 'in', OPEN_STATES),
            ('quantity_left', '>', 0),
            ('partner_id', '!=', self.partner_id.id),
            ('id', '!=', self.id),
        ]
        price_field = self._coop_price_field
        if self.order_type == 'limit':
            domain.append((price_field, '<=' if self.side == 'buy' else '>=', self._coop_price()))
        order = '%s %s, id' % (price_field, 'asc' if self.side == 'buy' else 'desc')
        candidates = self.sudo().search(domain, order=order)
        if candidates:
            # Две заявки, пришедшие одновременно, не должны исполниться об
            # одну и ту же встречную дважды.
            self.env.cr.execute(
                'SELECT id FROM %s WHERE id = ANY(%%s) FOR UPDATE' % self._table,
                [candidates.ids])
            candidates.invalidate_recordset(['quantity_left', 'state'])
            candidates = candidates.filtered(
                lambda o: o.state in OPEN_STATES and o.quantity_left > 0)
        return candidates

    def _coop_match(self):
        """Свести заявки со встречными. Возвращает заведённые исполнения."""
        Fill = self.env['coop.match.fill'].sudo()
        results = self.env['coop.match.fill']
        for order in self:
            if order.state not in OPEN_STATES or order.quantity_left <= 0:
                continue
            filled_any = False
            for maker in order._coop_opposite():
                left = order.quantity_left
                if left <= 1e-9:
                    break
                quantity = min(left, maker.quantity_left)
                price = maker._coop_price()
                order._coop_on_fill(maker, quantity, price)
                for side in (order, maker):
                    rest = max(side.quantity_left - quantity, 0.0)
                    side.sudo().write({
                        'quantity_left': rest,
                        'state': 'done' if rest <= 1e-9 else 'partial',
                    })
                results |= Fill._coop_append(order, maker, quantity, price)
                filled_any = True
            if order.order_type == 'market' and order.state in OPEN_STATES:
                # Рыночная заявка в стакане не остаётся.
                order.sudo().write({
                    'state': 'done' if filled_any else 'cancelled',
                    'quantity_left': 0.0,
                })
        return results

    @api.model
    def _coop_best_prices(self, domain):
        """Лучшая цена продажи и покупки на рынке — для «по рынку» и шапки."""
        price_field = self._coop_price_field
        base = list(domain) + [('state', 'in', OPEN_STATES), ('quantity_left', '>', 0)]
        ask = self.sudo().search(base + [('side', '=', 'sell')],
                                 order='%s asc, id' % price_field, limit=1)
        bid = self.sudo().search(base + [('side', '=', 'buy')],
                                 order='%s desc, id' % price_field, limit=1)
        return (ask[price_field] if ask else 0.0, bid[price_field] if bid else 0.0)


class CoopMatchFill(models.Model):
    """Исполнение заявки — неизменяемая запись журнала рынка.

    Номер в цепочке рынка, хэш предыдущего и хэш канонического тела —
    как у журнала узла (навык `federation-protocol`). Количество и цена —
    строками: дробные числа в теле подписи запрещены.
    """
    _name = 'coop.match.fill'
    _description = 'Исполнение заявки'
    _order = 'market, seq desc'

    market = fields.Char(string='Рынок', required=True, index=True, readonly=True)
    seq = fields.Integer(string='Номер', required=True, readonly=True)
    taker_model = fields.Char(string='Модель заявки', required=True, readonly=True)
    taker_id = fields.Integer(string='Заявка-инициатор', required=True, readonly=True)
    maker_id = fields.Integer(string='Встречная заявка', required=True, readonly=True)
    taker_partner_id = fields.Many2one('res.partner', string='Кто пришёл', readonly=True)
    maker_partner_id = fields.Many2one('res.partner', string='Чья стояла', readonly=True)
    side = fields.Selection([('buy', 'Покупка'), ('sell', 'Продажа')],
                            string='Сторона инициатора', readonly=True)
    quantity = fields.Float(string='Количество', digits=(16, 6), readonly=True)
    price = fields.Float(string='Цена', digits=(16, 6), readonly=True)
    date = fields.Datetime(string='Когда', required=True, readonly=True)
    prev_hash = fields.Char(string='Хэш предыдущего', readonly=True)
    hash = fields.Char(string='Хэш', required=True, readonly=True, index=True)

    @api.model
    def _coop_append(self, taker, maker, quantity, price, date=None):
        market = taker._coop_market_key()
        self.env.cr.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ['match:' + market])
        last = self.sudo().search([('market', '=', market)], order='seq desc', limit=1)
        seq = (last.seq or 0) + 1
        prev = last.hash or ''
        when = date or fields.Datetime.now()
        body = {
            'type': 'market.fill',
            'market': market,
            'taker': '%s:%s' % (taker._name, taker.id),
            'maker': '%s:%s' % (maker._name, maker.id),
            'side': taker.side,
            'quantity': num(quantity),
            'price': num(price),
            'at': fields.Datetime.to_string(when),
            'seq': seq,
            'prev': prev,
        }
        return self.sudo().with_context(coop_fill_append=True).create({
            'market': market, 'seq': seq,
            'taker_model': taker._name, 'taker_id': taker.id, 'maker_id': maker.id,
            'taker_partner_id': taker.partner_id.id, 'maker_partner_id': maker.partner_id.id,
            'side': taker.side, 'quantity': quantity, 'price': price, 'date': when,
            'prev_hash': prev, 'hash': hashlib.sha256(canonical(body)).hexdigest(),
        })

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('coop_fill_append'):
            raise UserError(_('Журнал исполнений пишется движком, а не вручную.'))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_('Запись журнала исполнений не меняется.'))

    def unlink(self):
        raise UserError(_('Запись журнала исполнений не удаляется.'))
