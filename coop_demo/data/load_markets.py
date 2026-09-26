# -*- coding: utf-8 -*-
"""История торгов для настоящих бирж (решение 417, этап 4).

Графикам нужна история: по каждой паре DEX — сделки за сто дней, по
двадцати самым торгуемым выпускам токеномики — за шестьдесят. Цена идёт
случайным блужданием от нынешних заявок, объём — по смыслу монеты.
Сделки пишутся и в журнал исполнений с цепочкой хэшей, по порядку дат.

Пересекающиеся заявки в стакане (покупка дороже продажи — наследие доски
объявлений) сводятся движком: это настоящие исполнения.

Однократно: отметка версии в параметрах.
"""
import logging
import random
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

VERSION = '1'
PARAM = 'coop_demo.market_history'

# Объём одной сделки по монете: от, до.
LOTS = {'BTC': (0.002, 0.08), 'ETH': (0.02, 1.2), 'USDT': (100, 4000), 'TON': (10, 600),
        'SOL': (0.5, 25), 'BNB': (0.05, 3)}


def _walk(rnd, start, days, vol):
    price, out = start, []
    for _day in range(days):
        price = max(price * (1 + rnd.gauss(0, vol)), start * 0.4)
        out.append(price)
    return out


def load_market_history(env):
    Param = env['ir.config_parameter'].sudo()
    if Param.get_param(PARAM) == VERSION:
        return 0
    if 'coop.match.fill' not in env:
        # Движок ещё не поставлен (загрузчик идёт раньше модулей бирж) —
        # отметку не ставим, наполним при следующем обновлении.
        return 0
    made = 0
    if 'coop.crypto.offer' in env and 'coop.match.fill' in env:
        made += _dex_history(env)
    if 'coop.token.order' in env and 'coop.match.fill' in env:
        made += _token_history(env)
    Param.set_param(PARAM, VERSION)
    _logger.info('Биржи: история торгов — %s сделок', made)
    return made


def _dex_history(env):
    Offer = env['coop.crypto.offer'].sudo()
    Trade = env['coop.crypto.trade'].sudo().with_context(tracking_disable=True,
                                                         mail_create_nolog=True)
    Fill = env['coop.match.fill'].sudo()
    people = env['res.partner'].sudo().search([('coop_is_participant', '=', True),
                                               ('is_company', '=', False)])
    now = datetime.now().replace(microsecond=0, second=0)
    made = 0
    groups = Offer._read_group([], ['asset', 'network_id'], ['__count'])
    for asset, network, _count in groups:
        rnd = random.Random('dex:%s:%s' % (asset, network.id))
        domain = [('asset', '=', asset), ('network_id', '=', network.id)]
        offers = Offer.search(domain)
        prices = sorted(offers.mapped('price'))
        if not prices:
            continue
        start = prices[len(prices) // 2] * rnd.uniform(0.85, 0.97)
        low, high = LOTS.get(asset, (1, 10))
        path = _walk(rnd, start, 100, 0.012 if asset != 'USDT' else 0.003)
        rows = []
        for back, price in zip(range(100, 0, -1), path):
            for _n in range(rnd.choice([0, 1, 1, 1, 2, 2, 3])):
                maker = rnd.choice(offers)
                taker = rnd.choice(people)
                if taker == maker.author_id:
                    continue
                # Последний день истории — в пределах суток: у пары есть
                # оборот и изменение за 24 часа.
                when = now - timedelta(days=back - 1, hours=rnd.randint(0, 22),
                                       minutes=rnd.randint(0, 59))
                amount = round(rnd.uniform(low, high), 6 if low < 1 else 2)
                state = 'done'
                if back <= 3:
                    state = rnd.choice(['done', 'agreed', 'rub_sent'])
                rows.append((when, maker, taker, round(price * rnd.uniform(0.997, 1.003), 2),
                             amount, state))
        rows.sort(key=lambda r: r[0])
        for when, maker, taker, price, amount, state in rows:
            methods = maker._coop_rub_methods() or {'sbp'}
            trade = Trade.create({
                'offer_id': maker.id, 'taker_id': taker.id, 'amount': amount, 'price': price,
                'rub_method': next(m for m in ('sbp', 'bank', 'cash') if m in methods),
                'date': when, 'state': state,
                'maker_confirmed': state == 'done', 'taker_confirmed': state == 'done',
            })
            taker_order = maker  # история: встречная заявка не сохранялась
            Fill._coop_append(_Taker(taker_order, taker, 'buy' if maker.side == 'sell' else 'sell'),
                              maker, amount, price, date=when)
            made += 1
        # Пересекающиеся заявки доски — свести по порядку выставления.
        crossing = Offer.search(domain + [('state', 'in', ('active', 'partial'))],
                                order='published_on, id')
        for offer in crossing:
            offer.invalidate_recordset(['state', 'quantity_left'])
            if offer.state in ('active', 'partial'):
                made += len(offer._coop_match())
    return made


class _Taker:
    """Заместитель заявки-инициатора для исторической записи журнала:
    встречная заявка в истории не хранилась, есть только сторона и
    участник."""

    def __init__(self, maker, partner, side):
        self._name = maker._name
        self.id = 0
        self.partner_id = partner
        self.side = side
        self._maker = maker

    def _coop_market_key(self):
        return self._maker._coop_market_key()


def _token_history(env):
    Order = env['coop.token.order'].sudo()
    Trade = env['coop.token.trade'].sudo()
    Fill = env['coop.match.fill'].sudo()
    now = datetime.now().replace(microsecond=0, second=0)
    groups = Order._read_group([('state', 'in', ('open', 'partial'))], ['claim_id'], ['__count'],
                               order='__count desc', limit=20)
    people = env['res.partner'].sudo().search([('coop_is_participant', '=', True),
                                               ('is_company', '=', False)])
    made = 0
    for claim, _count in groups:
        rnd = random.Random('token:%s' % claim.id)
        orders = Order.search([('claim_id', '=', claim.id)])
        base = claim.price_per_unit or (orders[:1].price_per_unit if orders else 0)
        if not base or not orders:
            continue
        path = _walk(rnd, base * rnd.uniform(0.9, 1.0), 60, 0.02)
        rows = []
        for back, price in zip(range(60, 0, -1), path):
            for _n in range(rnd.choice([0, 0, 1, 1, 2])):
                maker = rnd.choice(orders)
                other = rnd.choice(people)
                if other == maker.partner_id:
                    continue
                when = now - timedelta(days=back, hours=rnd.randint(8, 20))
                qty = round(rnd.uniform(1, max(2, (maker.quantity or 10) / 5)), 1)
                rows.append((when, maker, other, round(price, 2), qty))
        rows.sort(key=lambda r: r[0])
        for when, maker, other, price, qty in rows:
            seller = maker.partner_id if maker.side == 'sell' else other
            buyer = other if maker.side == 'sell' else maker.partner_id
            trade = Trade.create({
                'order_id': maker.id, 'claim_id': claim.id, 'seller_id': seller.id,
                'buyer_id': buyer.id, 'quantity': qty, 'price_per_unit': price,
                'state': 'done', 'confirmed_on': when, 'matched': True,
                'tx_hash': '%064x' % rnd.getrandbits(256),
            })
            env.cr.execute('UPDATE coop_token_trade SET create_date = %s WHERE id = %s',
                           [when, trade.id])
            Fill._coop_append(_Taker(maker, other, 'buy' if maker.side == 'sell' else 'sell'),
                              maker, qty, price, date=when)
            made += 1
    # Пересекающиеся заявки (покупка дороже продажи — наследие ручного
    # стакана) — свести по порядку выставления.
    for order in Order.search([('state', 'in', ('open', 'partial'))], order='create_date, id'):
        order.invalidate_recordset(['state', 'quantity_left'])
        if order.state in ('open', 'partial') and order.quantity_left > 0:
            made += len(order._coop_match())
    return made
