# -*- coding: utf-8 -*-
"""DEX биржа как действующая: глубокий стакан, история своих заявок и
пулы ликвидности под проекты (владелец 26.09.2026: «сделай современную
биржу и наполни примерами, сделай yield farming»).

1. Стакан. По каждой паре — не меньше тридцати заявок на продажу и
   тридцати на покупку лесенкой от лучших цен, объёмы по смыслу монеты.
   Заявки заводятся без сведения (`coop_no_match`): лесенка не
   пересекает спред, сводить нечего.
2. Витринный участник. Исполненные, частично исполненные и снятые заявки
   по верхним парам и обмены по ним — чтобы у «Истории заявок» и «Моих
   сделок» было что показать.
3. Фарминг. Пулы под настоящие проекты платформы: идущие сборы — под
   проекты в сборе, работающие — под запущенные, завершённые — под
   завершённые, несобранные — под часть отменённых. Во всех — взносы
   участников с разбросом сумм и дат; у витринного — позиции во всех
   состояниях.

Однократно: отметка версии в параметрах.
"""
import logging
import random
from datetime import date, datetime, timedelta

_logger = logging.getLogger(__name__)

VERSION = '1'
PARAM = 'coop_demo.dex_farm'

# Объём одной заявки в стакане: от, до (монет).
LOTS = {'BTC': (0.003, 0.35), 'ETH': (0.03, 4.0), 'USDT': (150, 12000), 'TON': (15, 2500),
        'SOL': (0.4, 60), 'BNB': (0.05, 9)}
DIGITS = {'BTC': 5, 'ETH': 3, 'USDT': 0, 'TON': 0, 'SOL': 2, 'BNB': 3}
# Цена ₽ — только для раскладки целей пулов, если у пары нет сделок.
PRICE = {'BTC': 8_600_000, 'ETH': 318_000, 'USDT': 93.4, 'TON': 492, 'SOL': 17_300,
         'BNB': 61_200}

TEST_NAMES = ('Danil', 'Proverka Vyhoda',
              'Игнатьев Денис Олегович', 'Прохорова Вера Андреевна')

PURPOSES = [
    'Оборотные средства: закупка оборудования у зарубежного поставщика по внешнеторговому '
    'контракту, возврат из выручки.',
    'Ликвидность пула в стакане DEX: проект обменивает выручку в цифровой валюте на рубли '
    'без посредников, пул получает спред.',
    'Предоплата поставщику из Китая за комплектующие — расчёт в цифровой валюте по '
    'внешнеторговому договору.',
    'Резерв на оплату серверов и лицензий у зарубежных провайдеров на год вперёд.',
    'Закупка материалов к сезону; проект выплачивает доход из продаж за шесть месяцев.',
    'Выкуп оборудования у лизинговой компании из ОАЭ, расчёт в USDT.',
    'Оплата работ подрядчику из Армении по контракту; доход — из поступлений по договорам.',
    'Мост ликвидности: проект получает монету сейчас и возвращает из платежей заказчиков.',
    'Покупка партии сырья у поставщика из Казахстана под подтверждённые заказы.',
    'Импортные материалы и доставка для стройки; выплаты — после сдачи этапа.',
    'Софинансирование: пул закрывает вторую половину сметы, первая — паевые взносы.',
    'Резерв на гарантийные выплаты участникам проекта на время запуска.',
    'Запчасти и расходники у зарубежного производителя — склад на полгода работы.',
    'Выход на экспорт: оплата сертификации и первой партии за рубежом.',
]

# Монета пула: (монета, код сети, вес).
POOL_COINS = [('USDT', 'ton', 30), ('USDT', 'eth', 16), ('USDT', 'bnb', 12), ('USDT', 'sol', 8),
              ('TON', 'ton', 16), ('BTC', 'btc', 6), ('ETH', 'eth', 7), ('SOL', 'sol', 3),
              ('BNB', 'bnb', 2)]
MIN_STAKE = {'USDT': (20, 50, 100, 500), 'TON': (5, 10, 50), 'BTC': (0.0005, 0.001),
             'ETH': (0.01, 0.05), 'SOL': (0.2, 1), 'BNB': (0.05, 0.1)}


def _round(value, asset):
    return round(value, DIGITS.get(asset, 2))


def load_dex_farm(env, login='dashkevich'):
    Param = env['ir.config_parameter'].sudo()
    if Param.get_param(PARAM) == VERSION:
        return 0
    if 'coop.farm.pool' not in env or 'coop.crypto.offer' not in env:
        return 0
    people = env['res.partner'].sudo().search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('name', 'not in', TEST_NAMES)])
    if len(people) < 20:
        return 0
    showcase = env['res.users'].sudo().search([('login', '=', login)], limit=1).partner_id
    crowd = people - showcase
    made = _deepen_books(env, crowd)
    made += _showcase_orders(env, crowd, showcase)
    made += _farm(env, crowd, showcase)
    Param.set_param(PARAM, VERSION)
    _logger.info('DEX биржа: стакан, история и фарминг — %s записей', made)
    return made


def _offer_env(env):
    return env['coop.crypto.offer'].sudo().with_context(
        coop_no_match=True, tracking_disable=True, mail_create_nolog=True, mail_notrack=True)


def _deepen_books(env, people):
    Offer = _offer_env(env)
    Trade = env['coop.crypto.trade'].sudo()
    now = datetime.now().replace(microsecond=0)
    made = 0
    groups = Offer._read_group([], ['asset', 'network_id'], ['__count'])
    for asset, network, _count in groups:
        rnd = random.Random('depth:%s:%s' % (asset, network.id))
        domain = [('asset', '=', asset), ('network_id', '=', network.id)]
        live = domain + [('state', 'in', ('active', 'partial')), ('quantity_left', '>', 0)]
        ask, bid = Offer._coop_best_prices(domain)
        if not ask or not bid:
            last = Trade.search(domain + [('state', 'in', ('agreed', 'rub_sent', 'done'))],
                                order='date desc', limit=1).price
            mid = last or ask or bid
            if not mid:
                continue
            ask = ask or mid * 1.0015
            bid = bid or mid * 0.9985
        if bid >= ask:
            # Стакан уже пересечён — лесенку не кладём, сведёт движок.
            continue
        # Лесенка идёт от лучших цен вглубь: продажи дороже лучшей продажи,
        # покупки дешевле лучшей покупки — спред не пересекается.
        top_ask, top_bid = ask, bid
        low, high = LOTS.get(asset, (1, 10))
        for side, start, sign in (('sell', top_ask, 1), ('buy', top_bid, -1)):
            have = Offer.search_count(live + [('side', '=', side)])
            need = max(0, rnd.randint(30, 42) - have)
            price = start
            for level in range(need):
                price = price * (1 + sign * rnd.uniform(0.0004, 0.0022) * (1 + level / 25))
                # Объём растёт вглубь стакана — крупные заявки дальше от цены.
                amount = _round(rnd.uniform(low, high) * rnd.choice([0.3, 0.6, 1, 1, 1.5, 2.5])
                                * (1 + level / 18), asset)
                if amount <= 0:
                    continue
                author = rnd.choice(people)
                cash = rnd.random() < 0.2
                Offer.create({
                    'side': side, 'asset': asset, 'network_id': network.id,
                    'author_id': author.id, 'price': round(price, 2),
                    'amount_min': 0.0, 'amount_max': amount,
                    'rub_sbp': rnd.random() < 0.8 or not cash,
                    'rub_bank': rnd.random() < 0.5, 'rub_cash': cash,
                    'city': author.city if cash else False,
                    'order_type': 'limit', 'state': 'active',
                    'published_on': now - timedelta(days=rnd.randint(0, 12),
                                                    hours=rnd.randint(0, 23),
                                                    minutes=rnd.randint(0, 59)),
                })
                made += 1
    return made


def _showcase_orders(env, people, showcase):
    if not showcase:
        return 0
    Offer = _offer_env(env)
    Trade = env['coop.crypto.trade'].sudo().with_context(
        tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    rnd = random.Random('showcase-orders')
    now = datetime.now().replace(microsecond=0)
    made = 0
    groups = Offer._read_group([('state', 'in', ('active', 'partial'))], ['asset', 'network_id'],
                               ['__count'], order='__count desc')
    for asset, network, _count in groups:
        domain = [('asset', '=', asset), ('network_id', '=', network.id)]
        ask, bid = Offer._coop_best_prices(domain)
        if not ask or not bid or bid >= ask:
            continue
        mid = (ask + bid) / 2
        low, high = LOTS.get(asset, (1, 10))
        plan = ['done', 'done', 'partial_closed', 'closed', 'done', 'open']
        for index, kind in enumerate(plan[:rnd.randint(3, 6)]):
            side = rnd.choice(['buy', 'sell'])
            back = rnd.randint(2, 80)
            price = round(mid * rnd.uniform(0.9, 1.06), 2)
            amount = _round(rnd.uniform(low, high / 3), asset) or _round(high / 10, asset)
            if kind == 'open':
                # Открытая заявка за лучшей встречной ценой — ждёт встречной.
                price = round(bid * 0.99 if side == 'buy' else ask * 1.01, 2)
            filled = {'done': amount, 'partial_closed': _round(amount * rnd.uniform(0.2, 0.7), asset),
                      'closed': 0.0, 'open': 0.0}[kind]
            state = {'done': 'done', 'partial_closed': 'closed', 'closed': 'closed',
                     'open': 'active'}[kind]
            when = now - timedelta(days=back if kind != 'open' else rnd.randint(0, 3),
                                   hours=rnd.randint(0, 23))
            offer = Offer.create({
                'side': side, 'asset': asset, 'network_id': network.id,
                'author_id': showcase.id, 'price': price, 'amount_min': 0.0,
                'amount_max': amount, 'rub_sbp': True, 'rub_bank': rnd.random() < 0.6,
                'order_type': 'limit', 'state': state, 'published_on': when,
            })
            offer.sudo().write({'quantity_left': max(amount - filled, 0.0) if state != 'done' else 0.0})
            made += 1
            if filled > 0:
                taker = rnd.choice(people)
                if taker == showcase:
                    continue
                Trade.create({
                    'offer_id': offer.id, 'taker_id': taker.id, 'amount': filled, 'price': price,
                    'rub_method': rnd.choice(['sbp', 'bank']),
                    'date': when + timedelta(minutes=rnd.randint(3, 600)),
                    'state': 'done', 'maker_confirmed': True, 'taker_confirmed': True,
                })
                made += 1
    return made


def _farm(env, people, showcase):
    Pool = env['coop.farm.pool'].sudo()
    Stake = env['coop.farm.stake'].sudo()
    if Pool.search_count([], limit=1):
        return 0
    rnd = random.Random('farm-20260926')
    today = date.today()
    now = datetime.now().replace(microsecond=0)
    networks = {n.code: n for n in env['coop.wallet.network'].sudo().search([])}
    Project = env['coop.project'].sudo()
    plan = []
    for state, pool_state, limit in (('gathering', 'raising', 72), ('running', 'active', 25),
                                     ('done', 'closed', 20), ('cancelled', 'refunded', 9),
                                     ('frozen', 'raising', 3)):
        projects = Project.search([('state', '=', state)], order='id')
        picked = rnd.sample(list(projects), min(limit, len(projects)))
        plan += [(p, pool_state) for p in picked]
    rnd.shuffle(plan)
    prices = {}
    made = 0
    my_left = {'raising': 3, 'active': 2, 'closed': 2, 'refunded': 1}
    for project, pool_state in plan:
        asset, code, _w = rnd.choices(POOL_COINS, weights=[c[2] for c in POOL_COINS])[0]
        network = networks.get(code)
        if not network:
            continue
        key = (asset, network.id)
        if key not in prices:
            trade = env['coop.crypto.trade'].sudo().search(
                [('asset', '=', asset), ('network_id', '=', network.id)], order='date desc', limit=1)
            prices[key] = trade.price or PRICE[asset]
        price = prices[key]
        target_rub = rnd.choice([300_000, 500_000, 800_000, 1_200_000, 2_000_000, 3_500_000,
                                 5_000_000, 8_000_000, 15_000_000]) * rnd.uniform(0.8, 1.2)
        target = target_rub / price
        target = round(target, -2) if asset == 'USDT' and target > 1000 else _round(target, asset)
        if asset == 'TON':
            target = round(target, -1)
        apr_project = round(rnd.uniform(4, 26), 1)
        apr_fee = round(rnd.uniform(1.2, 8.5), 1)
        total = apr_project + apr_fee
        readiness = project.readiness or 0
        risk = 'high' if total > 26 or readiness < 20 else 'low' if total < 13 and readiness > 50 \
            else 'medium'
        lock = rnd.choice([90, 120, 180, 180, 270, 365])
        if pool_state == 'raising':
            start = today - timedelta(days=rnd.randint(1, 55))
            deadline = today + timedelta(days=rnd.choice([1, 2, 5, 9, 14, 21, 30, 45, 60]))
            progress = rnd.choice([0.05, 0.12, 0.25, 0.4, 0.55, 0.68, 0.8, 0.9, 0.97])
            date_end = False
        elif pool_state == 'active':
            start = today - timedelta(days=rnd.randint(40, 200))
            deadline = start + timedelta(days=rnd.randint(20, 45))
            lock = max(lock, (today - deadline).days + rnd.randint(20, 200))
            progress = 1.0
            date_end = deadline + timedelta(days=lock)
        elif pool_state == 'closed':
            start = today - timedelta(days=rnd.randint(260, 520))
            deadline = start + timedelta(days=rnd.randint(20, 45))
            lock = rnd.choice([90, 120, 180])
            date_end = deadline + timedelta(days=lock)
            if date_end >= today:
                date_end = today - timedelta(days=rnd.randint(3, 60))
            progress = 1.0
        else:  # refunded
            start = today - timedelta(days=rnd.randint(70, 200))
            deadline = start + timedelta(days=rnd.randint(30, 60))
            progress = rnd.choice([0.15, 0.3, 0.45, 0.6])
            date_end = False
        pool = Pool.create({
            'project_id': project.id, 'asset': asset, 'network_id': network.id,
            'purpose': rnd.choice(PURPOSES), 'target': target,
            'min_stake': rnd.choice(MIN_STAKE[asset]),
            'apr_fee': apr_fee, 'apr_project': apr_project, 'lock_days': lock,
            'date_start': start, 'date_deadline': deadline, 'date_end': date_end,
            'state': pool_state, 'risk': risk,
        })
        made += 1
        # Взносы: сумма — цель × собранная доля, раскладка неровная.
        raised = target * progress
        count = max(2, min(40, int(rnd.uniform(3, 28) * (0.4 + progress))))
        weights = [rnd.paretovariate(1.4) for _ in range(count)]
        scale = raised / sum(weights)
        last_day = min(deadline, today) if pool_state != 'raising' else today
        span = max((last_day - start).days, 1)
        stakers = rnd.sample(list(people), min(count, len(people)))
        include_me = showcase and my_left.get(pool_state, 0) > 0 and rnd.random() < 0.35
        if include_me:
            my_left[pool_state] -= 1
            stakers[0] = showcase
        rest = raised
        for index, partner in enumerate(stakers):
            amount = rest if index == len(stakers) - 1 else _round(weights[index] * scale, asset)
            amount = _round(max(amount, pool.min_stake or 0), asset)
            if amount <= 0 or rest <= 0:
                break
            amount = min(amount, _round(rest, asset)) if index < len(stakers) - 1 else _round(rest, asset)
            if amount <= 0:
                break
            rest -= amount
            when = datetime.combine(start + timedelta(days=rnd.randint(0, span - 1 if span > 1 else 0)),
                                    datetime.min.time()) + timedelta(hours=rnd.randint(8, 22),
                                                                     minutes=rnd.randint(0, 59))
            when = min(when, now - timedelta(minutes=5))
            vals = {'pool_id': pool.id, 'partner_id': partner.id, 'amount': amount, 'date': when,
                    'tx_hash': '%064x' % rnd.getrandbits(256)}
            if pool_state in ('closed', 'refunded'):
                # Закрытые: почти все вывели; у витринного один взнос — ещё к выводу.
                keep = partner == showcase and pool_state == 'closed'
                if not keep and rnd.random() < 0.92:
                    vals.update({'state': 'withdrawn',
                                 'withdrawn_on': datetime.combine(date_end or deadline,
                                                                  datetime.min.time())
                                 + timedelta(days=rnd.randint(0, 6), hours=rnd.randint(9, 20))})
            stake = Stake.create(vals)
            earned = stake._earned()
            if stake.state == 'withdrawn':
                stake.harvested = earned
            elif pool_state in ('active', 'closed'):
                stake.harvested = round(earned * rnd.choice([0, 0.2, 0.5, 0.8, 0.95]), 8)
            made += 1
    return made
