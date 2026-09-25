# -*- coding: utf-8 -*-
"""Обмен цифровой валюты — объявления и обмены (решение 392).

Каталог наполняется не менее чем сотней-двумя примеров: здесь сто
пятьдесят объявлений и сто тридцать обменов. Раскладка неровная:

- продают и покупают; шесть монет, USDT — в четырёх сетях;
- цены вокруг рыночной с разбросом в пару процентов в обе стороны;
- пределы от мелких до крупных — часть объявлений выше порога
  подтверждения личности;
- способы рублёвого расчёта — СБП, перевод, наличные при встрече (у
  наличных — город);
- объявления активные, на паузе и снятые;
- обмены состоявшиеся, отменённые, идущие и спорные.

Цены — ориентир на сентябрь 2026 года, не котировка: платформа курс не
устанавливает.

Повторный запуск ничего не добавляет.
"""
import logging
import random
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

TEST_NAMES = ('Danil', 'Proverka Vyhoda',
              'Игнатьев Денис Олегович', 'Прохорова Вера Андреевна')

# Монета: (цена ₽, пределы «от» и «до» в единицах, сети).
MARKET = {
    'BTC': (8_600_000, (0.0005, 0.003), (0.005, 0.06), ('btc',)),
    'ETH': (318_000, (0.01, 0.05), (0.1, 1.5), ('eth',)),
    'USDT': (93.4, (20, 200), (300, 5000), ('eth', 'ton', 'bnb', 'sol')),
    'TON': (492, (10, 50), (100, 1200), ('ton',)),
    'SOL': (17_300, (0.1, 1), (1, 25), ('sol',)),
    'BNB': (61_200, (0.05, 0.3), (0.5, 7), ('bnb',)),
}
WEIGHTS = {'USDT': 40, 'BTC': 18, 'TON': 16, 'ETH': 12, 'SOL': 8, 'BNB': 6}

TERMS = [
    'Первым переводит тот, у кого выше уровень доверия. Жду 2 подтверждения сети.',
    'Сначала рубли, потом монеты — по истории сделок на платформе.',
    'Работаю вечером после 19:00. Перевод в течение 15 минут.',
    'Для суммы больше 300 000 ₽ — встреча и подтверждение личности.',
    'Только с участниками, у которых подтверждена личность.',
    'Частями: первая треть, после подтверждения — остальное.',
    '',
]


def _round_amount(value, asset):
    if asset in ('USDT', 'TON'):
        return round(value, 0)
    if asset in ('SOL', 'BNB', 'ETH'):
        return round(value, 2)
    return round(value, 4)


def load_crypto(env, login='dashkevich', offers=150, trades=130):
    if 'coop.crypto.offer' not in env:
        return 0
    Offer = env['coop.crypto.offer'].sudo().with_context(
        tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    Trade = env['coop.crypto.trade'].sudo().with_context(
        tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    if Offer.search_count([], limit=1):
        _logger.info('Обмен цифровой валюты: уже наполнено, пропускаю')
        return 0
    rnd = random.Random(20260925 + 3922)
    now = datetime.now().replace(microsecond=0)
    people = env['res.partner'].sudo().search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('name', 'not in', TEST_NAMES)])
    if len(people) < 20:
        return 0
    networks = {n.code: n for n in env['coop.wallet.network'].sudo().search([])}
    showcase = env['res.users'].sudo().search([('login', '=', login)], limit=1).partner_id

    made = []
    for index in range(offers):
        asset = rnd.choices(list(WEIGHTS), weights=list(WEIGHTS.values()))[0]
        price, low, high, nets = MARKET[asset]
        code = rnd.choice(nets)
        if code not in networks:
            continue
        side = rnd.choices(['sell', 'buy'], weights=[55, 45])[0]
        # Продают чуть дороже рынка, покупают чуть дешевле.
        spread = rnd.uniform(0.004, 0.03) * (1 if side == 'sell' else -1)
        author = showcase if showcase and index < 4 else rnd.choice(people)
        amount_min = _round_amount(rnd.uniform(*low), asset)
        amount_max = _round_amount(rnd.uniform(*high) * rnd.choice([1, 1, 1, 2, 4]), asset)
        cash = rnd.random() < 0.3
        sbp = rnd.random() < 0.75 or not cash
        state = rnd.choices(['active', 'paused', 'closed'], weights=[80, 10, 10])[0]
        offer = Offer.create({
            'side': side,
            'asset': asset,
            'network_id': networks[code].id,
            'author_id': author.id,
            'price': round(price * (1 + spread), 2),
            'amount_min': amount_min,
            'amount_max': max(amount_max, amount_min * 2),
            'rub_sbp': sbp,
            'rub_bank': rnd.random() < 0.45,
            'rub_cash': cash,
            'city': author.city if cash else False,
            'terms': rnd.choice(TERMS) or False,
            'state': 'active' if author == showcase else state,
            'published_on': now - timedelta(days=rnd.randint(0, 60), hours=rnd.randint(0, 23)),
        })
        made.append(offer)

    done_trades = 0
    for index in range(trades):
        offer = rnd.choice(made)
        taker = showcase if showcase and index < 8 and offer.author_id != showcase \
            else rnd.choice(people)
        if taker == offer.author_id:
            continue
        methods = [m for m, flag in (('sbp', offer.rub_sbp), ('bank', offer.rub_bank),
                                     ('cash', offer.rub_cash)) if flag]
        amount = _round_amount(rnd.uniform(offer.amount_min or offer.amount_max / 10,
                                           offer.amount_max), offer.asset)
        state = rnd.choices(['done', 'cancelled', 'agreed', 'rub_sent', 'disputed'],
                            weights=[55, 15, 12, 10, 8])[0]
        start = offer.published_on or now - timedelta(days=30)
        when = start + (now - start) * rnd.uniform(0.05, 0.98)
        Trade.create({
            'offer_id': offer.id,
            'taker_id': taker.id,
            'amount': amount,
            'price': offer.price,
            'rub_method': rnd.choice(methods),
            'date': when.replace(microsecond=0),
            'state': state,
            'maker_confirmed': state == 'done',
            'taker_confirmed': state in ('done', 'rub_sent') and rnd.random() < 0.9,
        })
        done_trades += 1

    _logger.info('Обмен цифровой валюты: объявлений %s, обменов %s', len(made), done_trades)
    return len(made)
