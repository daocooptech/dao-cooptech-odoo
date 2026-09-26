# -*- coding: utf-8 -*-
"""Экран DEX биржи: пары, стакан, сделки, свечи — одним снимком.

Решение 417: DEX — настоящая биржа со сведением заявок. Пара — монета в
своей сети к рублю («USDT · TON / RUB»): одна и та же монета в разных сетях
— разные рынки, перевод в чужую сеть означает потерю средств.
"""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

TRADE_LIVE = ('agreed', 'rub_sent', 'done', 'disputed')


class CoopCryptoMarket(models.AbstractModel):
    _name = 'coop.crypto.market'
    _description = 'DEX биржа: данные экрана'

    def _pairs(self):
        Offer = self.env['coop.crypto.offer'].sudo()
        groups = Offer._read_group([('state', 'in', ('active', 'partial'))],
                                   ['asset', 'network_id'], ['__count'])
        return [(asset, network, count) for asset, network, count in groups]

    @api.model
    def markets(self):
        Offer = self.env['coop.crypto.offer']
        Trade = self.env['coop.crypto.trade'].sudo()
        day_ago = fields.Datetime.now() - timedelta(days=1)
        rows = []
        for asset, network, count in self._pairs():
            domain = [('asset', '=', asset), ('network_id', '=', network.id)]
            ask, bid = Offer._coop_best_prices(domain)
            trades = Trade.search(domain + [('state', 'in', TRADE_LIVE)], order='date desc',
                                  limit=200)
            last = trades[:1].price if trades else (ask or bid)
            day = trades.filtered(lambda t: t.date >= day_ago)
            before = trades.filtered(lambda t: t.date < day_ago)[:1]
            change = ((last - before.price) / before.price * 100) if before and before.price else 0.0
            rows.append({
                'key': '%s:%s' % (asset, network.id),
                'asset': asset, 'network_id': network.id, 'network': network.name,
                'label': '%s · %s' % (asset, network.name) if asset == 'USDT' else asset,
                'ask': ask, 'bid': bid, 'last': last, 'change': change,
                'volume': sum(day.mapped('total')), 'orders': count,
            })
        rows.sort(key=lambda r: -r['volume'])
        return rows

    @api.model
    def book(self, asset, network_id):
        Offer = self.env['coop.crypto.offer']
        Trade = self.env['coop.crypto.trade'].sudo()
        me = self.env.user.partner_id
        domain = [('asset', '=', asset), ('network_id', '=', network_id)]
        live = domain + [('state', 'in', ('active', 'partial')), ('quantity_left', '>', 0)]

        def row(offer):
            return {
                'id': offer.id, 'price': offer.price, 'amount': offer.quantity_left,
                'total': offer.price * offer.quantity_left,
                'partner': offer.author_id.name, 'trust': offer.trust,
                'methods': offer.methods_label, 'mine': offer.author_id == me,
            }

        asks = Offer.sudo().search(live + [('side', '=', 'sell')], order='price asc, id', limit=40)
        bids = Offer.sudo().search(live + [('side', '=', 'buy')], order='price desc, id', limit=40)
        trades = Trade.search(domain + [('state', 'in', TRADE_LIVE)], order='date desc', limit=40)
        ask, bid = Offer._coop_best_prices(domain)
        mine = Offer.sudo().search(live + [('author_id', '=', me.id)], order='id desc')
        return {
            'asks': [row(o) for o in asks],
            'bids': [row(o) for o in bids],
            'best_ask': ask, 'best_bid': bid,
            'trades': [{
                'id': t.id, 'price': t.price, 'amount': t.amount, 'total': t.total,
                'when': fields.Datetime.to_string(t.date), 'state': t.state,
                'side': 'buy' if t.side == 'sell' else 'sell',
            } for t in trades],
            'candles': self._candles(domain),
            'mine': [row(o) | {'side': o.side, 'state': o.state} for o in mine],
        }

    def _candles(self, domain, days=120):
        Trade = self.env['coop.crypto.trade'].sudo()
        since = fields.Datetime.now() - timedelta(days=days)
        trades = Trade.search(domain + [('state', 'in', TRADE_LIVE), ('date', '>=', since)],
                              order='date, id')
        by_day = {}
        for t in trades:
            day = fields.Date.to_string(t.date.date())
            c = by_day.get(day)
            if not c:
                by_day[day] = {'day': day, 'o': t.price, 'h': t.price, 'l': t.price,
                               'c': t.price, 'v': t.amount}
            else:
                c['h'] = max(c['h'], t.price)
                c['l'] = min(c['l'], t.price)
                c['c'] = t.price
                c['v'] += t.amount
        return [by_day[d] for d in sorted(by_day)]

    @api.model
    def place_order(self, asset, network_id, side, order_type, amount, price=None, methods=None):
        """Выставить заявку и свести со встречными (решение 417)."""
        amount = float(amount or 0)
        if amount <= 0:
            raise UserError(_('Укажите, сколько.'))
        methods = set(methods or [])
        if not methods & {'sbp', 'bank', 'cash'}:
            raise UserError(_('Отметьте хотя бы один способ расчёта рублями.'))
        Offer = self.env['coop.crypto.offer']
        domain = [('asset', '=', asset), ('network_id', '=', network_id)]
        if order_type == 'market':
            ask, bid = Offer._coop_best_prices(domain)
            price = ask if side == 'buy' else bid
            if not price:
                raise UserError(_('Встречных заявок нет — выставьте лимитную.'))
        price = float(price or 0)
        if price <= 0:
            raise UserError(_('Укажите цену.'))
        offer = Offer.create({
            'side': side, 'asset': asset, 'network_id': network_id,
            'order_type': 'market' if order_type == 'market' else 'limit',
            'author_id': self.env.user.partner_id.id,
            'price': price, 'amount_min': 0.0, 'amount_max': amount,
            'rub_sbp': 'sbp' in methods, 'rub_bank': 'bank' in methods,
            'rub_cash': 'cash' in methods,
        })
        trades = self.env['coop.crypto.trade'].sudo().search([('taker_offer_id', '=', offer.id)])
        return {
            'offer_id': offer.id,
            'filled': sum(trades.mapped('amount')),
            'trades': trades.ids,
            'left': offer.quantity_left if offer.state in ('active', 'partial') else 0.0,
            'state': offer.state,
        }
