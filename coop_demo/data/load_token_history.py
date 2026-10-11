# -*- coding: utf-8 -*-
"""История торгов на бирже токенов — чтобы у рынков были настоящие графики.

Замечание владельца 11.10.2026: в «Токеномике» должны быть графики, как на
настоящей бирже. На графике должно быть что рисовать: у большинства
рынков было по одной-четырём сделкам, свечи не набирались.

Проход достраивает каждому рынку историю прошедших сделок за 70–180 дней:
у ходовых рынков — по несколько сделок в день, у средних — одна-две,
у тонких — раз в несколько дней, с
разной волатильностью. Цена идёт назад от текущей рыночной случайным
блужданием, которое тянет к цене выпуска, — поэтому последняя цена и
«изменение» в списке рынков остаются прежними, а график к ним приходит
естественно, а не обрывается.

Безвреден при повторе: рынок с уже достроенной историей (у её сделок есть
удержанная комиссия сети) пропускается; генератор у каждого рынка свой.
"""
import logging
import math
import random
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

# (доля рынков, сделок в день от/до, дней истории, волатильность за сделку,
#  сила притяжения к цене выпуска). Чем плотнее торги, тем меньше шаг цены
# за сделку: дневной размах получается разумным у всех трёх видов рынков.
TIERS = [
    (0.12, (3.0, 7.0), 120, 0.007, 0.004),
    (0.38, (0.8, 2.0), 100, 0.013, 0.015),
    (0.50, (0.3, 0.8), 70, 0.025, 0.04),
]


def load_token_history(env):
    if 'coop.token.trade' not in env:
        return 0
    Claim = env['coop.token.claim'].sudo()
    Trade = env['coop.token.trade'].sudo().with_context(
        tracking_disable=True, mail_notrack=True, mail_create_nolog=True)
    traders = env['res.partner'].sudo().search(
        [('coop_ton_address', '!=', False)], limit=400)
    if len(traders) < 6:
        return 0
    now = datetime.now().replace(microsecond=0)
    made = 0
    # Те же двести рынков и в том же порядке, что показывает биржа.
    claims = Claim.search(
        [('state', 'in', ('trading', 'delivering', 'minted'))],
        order='delivery_date', limit=200)
    for claim in claims:
        # Метка готовой истории — удержанная комиссия сети: в прежнем
        # наполнении её не было ни у одной сделки.
        if Trade.search_count([
                ('claim_id', '=', claim.id), ('network_fee', '>', 0)],
                limit=1):
            continue
        order = env['coop.token.order'].sudo().search(
            [('claim_id', '=', claim.id)], limit=1, order='id')
        if not order or not claim.price_per_unit:
            continue
        rnd = random.Random(20261012 + claim.id)
        pick = rnd.random()
        edge = 0.0
        for share, rate, days, sigma, pull_k in TIERS:
            edge += share
            if pick < edge:
                break
        count = max(int(rnd.uniform(*rate) * days), 7)
        last = Trade.search([('claim_id', '=', claim.id), ('state', '=', 'done')],
                            order='confirmed_on desc', limit=1)
        if last and last.confirmed_on:
            end_time = min(last.confirmed_on, now) - timedelta(hours=rnd.randint(2, 30))
            end_price = last.price_per_unit
        else:
            end_time = now - timedelta(hours=rnd.randint(3, 60))
            end_price = round(claim.price_per_unit * rnd.uniform(0.9, 1.15), 4)
        # Моменты сделок идут от конца назад: чаще у конца (рынок живее),
        # реже в глубине истории.
        stamps, cursor = [], end_time
        mean_gap = days * 24 * 3600 / count
        for _ in range(count):
            stamps.append(cursor)
            cursor -= timedelta(seconds=max(60, rnd.expovariate(1 / mean_gap)))
        anchor = claim.price_per_unit
        price, rows = end_price, []
        for when in stamps:
            seller, buyer = rnd.sample(list(traders), 2)
            quantity = round(max(claim.quantity, 1) * rnd.uniform(0.002, 0.03), 3) or 1
            rows.append({
                'order_id': order.id,
                'claim_id': claim.id,
                'seller_id': seller.id,
                'buyer_id': buyer.id,
                'quantity': quantity,
                'price_per_unit': max(round(price, 4), 0.0001),
                'state': 'done',
                'network_fee': round(rnd.uniform(0.008, 0.02), 6),
                'tx_hash': ''.join(rnd.choice('0123456789abcdef') for _ in range(64)),
                'confirmed_on': when,
            })
            # Шаг назад: шум и тяга к цене выпуска.
            pull = pull_k * math.log(price / anchor) if anchor else 0.0
            price *= math.exp(rnd.gauss(0, sigma) - pull)
            price = min(max(price, anchor * 0.45), anchor * 2.2)
        Trade.create(rows)
        made += len(rows)
    _logger.info('История торгов токенов: достроено сделок %s', made)
    return made
