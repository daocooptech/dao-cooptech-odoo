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
3. Пулы проектов (версия 2, решения 434–436, 28.09.2026): сбор под
   проект с долей выручки и потолком, два вида — в монете (~130) и в
   рублях через ЦФА, учебный выпуск (~110). Идущие сборы — под проекты в
   сборе; с выплатами — под запущенные: записанные инициатором выплаты,
   подтверждённые, ждущие подтверждения, оспоренные; просрочки по графику
   и невозвраты; завершённые — потолок выплачен или вышел срок;
   несобранные — возврат. Под замороженными проектами сборов нет (434,
   п. 8) — только пулы, собранные до заморозки.
4. Возврат комиссии DEX (0,1 %, половина — торговавшим по обороту) за
   прошедшие месяцы с обменами.

Отметка версии в параметрах. Переход с версии 1: стакан и история не
трогаются, пулы загрузчика (создатель — система, ручных среди них нет —
проверено на боевой 28.09) пересобираются целиком: в прежних не было ни
доли выручки, ни выплат, и дописать их по количеству нельзя.
"""
import logging
import random
from datetime import date, datetime, timedelta

_logger = logging.getLogger(__name__)

VERSION = '2'
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
    current = Param.get_param(PARAM)
    if current == VERSION:
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
    made = 0
    if not current:
        made += _deepen_books(env, crowd)
        made += _showcase_orders(env, crowd, showcase)
    made += _farm(env, crowd, showcase)
    made += _rebates(env)
    Param.set_param(PARAM, VERSION)
    _logger.info('DEX биржа: стакан, история, пулы проектов и возвраты — %s записей', made)
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


RUB_PURPOSES = [
    'Оборотные средства на закупку сырья под подтверждённые заказы; возврат из выручки.',
    'Новая линия фасовки: оборудование и пусконаладка, выплаты — из продаж продукции.',
    'Ремонт и оснащение цеха; доля выручки цеха — участникам до потолка.',
    'Закупка техники к сезону; выплаты из выручки за услуги техники.',
    'Открытие второй точки продаж кооператива; доля выручки точки.',
    'Софинансирование проекта: вторая половина сметы, первая — паевые взносы.',
    'Склад и холодильная камера под урожай; выплаты — из хранения и продаж.',
    'Сертификация продукции и первая партия на маркетплейсы.',
    'Модернизация пекарни: печь и тестомес, выплаты из выручки пекарни.',
    'Мастерская по ремонту техники: инструмент и запас запчастей.',
]
RUB_MIN = (500, 1000, 1000, 3000, 5000, 10000)
CAPS = (1.1, 1.15, 1.2, 1.25, 1.3, 1.3, 1.4, 1.5)
# Молчание участника столько дней — выплата получена (решение 436, п. 6).
CONFIRM_DAYS_DEMO = 14
# Раскладка пулов по состояниям: (состояние пула, состояния проекта, сколько).
COIN_PLAN = [('raising', ('gathering',), 55), ('active', ('running',), 30),
             ('overdue', ('running',), 7), ('overdue', ('frozen',), 2),
             ('default', ('running', 'frozen'), 4), ('closed', ('done', 'running'), 22),
             ('refunded', ('cancelled',), 11)]
RUB_PLAN = [('raising', ('gathering',), 45), ('active', ('running',), 24),
            ('overdue', ('running',), 6), ('overdue', ('frozen',), 1),
            ('default', ('running', 'frozen'), 3), ('closed', ('done', 'running'), 20),
            ('refunded', ('cancelled',), 11)]


def _farm(env, people, showcase):
    """Пулы проектов заново: пулы загрузчика (создатель — система) сносятся
    со взносами и выплатами, собираются новые обоих видов."""
    Pool = env['coop.farm.pool'].sudo().with_context(coop_farm_loader=True)
    Stake = env['coop.farm.stake'].sudo()
    Pool.search([('create_uid', '=', env.ref('base.user_root').id)]).unlink()
    rnd = random.Random('pools-20260928')
    today = date.today()
    now = datetime.now().replace(microsecond=0)
    networks = {n.code: n for n in env['coop.wallet.network'].sudo().search([])}
    Project = env['coop.project'].sudo()
    by_state = {}
    for state in ('gathering', 'running', 'done', 'cancelled', 'frozen'):
        by_state[state] = list(Project.search([('state', '=', state)], order='id'))
    mine_projects = [p for p in by_state['running'] if showcase and p.partner_id == showcase]
    prices = {}
    made = 0
    my_left = {'raising': 3, 'active': 3, 'overdue': 1, 'closed': 1, 'refunded': 1}
    for kind, plan in (('coin', COIN_PLAN), ('rub', RUB_PLAN)):
        used = set()
        for pool_state, project_states, count in plan:
            pool_projects = [p for s in project_states for p in by_state[s]]
            if not pool_projects:
                continue
            fresh = [p for p in pool_projects if p.id not in used]
            for index in range(count):
                if kind == 'coin' and pool_state == 'active' and index == 0 and mine_projects:
                    project = mine_projects[0]      # витринный — инициатор своего пула
                elif fresh:
                    project = fresh.pop(rnd.randrange(len(fresh)))
                else:
                    project = rnd.choice(pool_projects)
                used.add(project.id)
                pool, periods = _make_pool(env, Pool, rnd, today, kind, pool_state, project,
                                           networks, prices)
                if not pool:
                    continue
                made += 1
                made += _make_stakes(Stake, rnd, today, now, pool, pool_state, people, showcase,
                                     my_left)
                made += _make_payouts(pool, rnd, today, pool_state, periods, showcase)
    return made


def _make_pool(env, Pool, rnd, today, kind, pool_state, project, networks, prices):
    if kind == 'coin':
        asset, code, _w = rnd.choices(POOL_COINS, weights=[c[2] for c in POOL_COINS])[0]
        network = networks.get(code)
        if not network:
            return None, 0
        key = (asset, network.id)
        if key not in prices:
            trade = env['coop.crypto.trade'].sudo().search(
                [('asset', '=', asset), ('network_id', '=', network.id)], order='date desc', limit=1)
            prices[key] = trade.price or PRICE[asset]
        price = prices[key]
    else:
        asset, network, price = False, False, 1.0
    target_rub = rnd.choice([300_000, 500_000, 800_000, 1_200_000, 2_000_000, 3_500_000,
                             5_000_000, 8_000_000, 15_000_000]) * rnd.uniform(0.8, 1.2)
    if kind == 'coin':
        target = target_rub / price
        target = round(target, -2) if asset == 'USDT' and target > 1000 else _round(target, asset)
        if asset == 'TON':
            target = round(target, -1)
        min_stake = rnd.choice(MIN_STAKE[asset])
    else:
        target = round(target_rub, -4)
        min_stake = rnd.choice(RUB_MIN)
    share = rnd.choice([2, 3, 4, 5, 5, 6, 7, 8, 10, 12, 15])
    cap = rnd.choice(CAPS)
    readiness = project.readiness or 0
    risk = 'high' if cap >= 1.4 or readiness < 20 else 'low' if cap <= 1.2 and readiness > 50 \
        else 'medium'
    payout_days = rnd.choice([30, 30, 30, 90])
    lock = rnd.choice([365, 540, 730, 730, 1095])
    vals = {
        'kind': kind, 'project_id': project.id, 'asset': asset,
        'network_id': network.id if network else False,
        'purpose': rnd.choice(PURPOSES if kind == 'coin' else RUB_PURPOSES),
        'target': target, 'min_stake': min_stake, 'revenue_share': share,
        'cap_multiple': cap, 'payout_days': payout_days, 'lock_days': lock, 'risk': risk,
    }
    periods = 0
    if pool_state == 'raising':
        vals.update({'date_start': today - timedelta(days=rnd.randint(1, 55)),
                     'date_deadline': today + timedelta(days=rnd.choice([1, 2, 5, 9, 14, 21, 30, 45, 60])),
                     'state': 'raising'})
    elif pool_state == 'refunded':
        start = today - timedelta(days=rnd.randint(70, 240))
        vals.update({'date_start': start, 'date_deadline': start + timedelta(days=rnd.randint(30, 60)),
                     'state': 'refunded'})
    else:
        # Сколько выплат уже прошло по графику — от этого дата сбора.
        periods = {'active': rnd.randint(1, 10), 'overdue': rnd.randint(3, 9),
                   'default': rnd.randint(3, 7), 'closed': rnd.randint(8, 16)}[pool_state]
        back = periods * payout_days + rnd.randint(0, payout_days - 1)
        if pool_state == 'overdue':
            back += rnd.randint(10, 150)
        elif pool_state == 'default':
            back += rnd.randint(185, 320)
        activated = today - timedelta(days=back)
        start = activated - timedelta(days=rnd.randint(20, 50))
        vals.update({'date_start': start, 'date_deadline': activated,
                     'date_activated': activated,
                     'date_end': activated + timedelta(days=max(lock, back + 30)),
                     'state': 'active'})
    return Pool.create(vals), periods


def _make_stakes(Stake, rnd, today, now, pool, pool_state, people, showcase, my_left):
    asset = pool.asset or 'RUB'
    progress = {'raising': rnd.choice([0.05, 0.12, 0.25, 0.4, 0.55, 0.68, 0.8, 0.9, 0.97]),
                'refunded': rnd.choice([0.15, 0.3, 0.45, 0.6])}.get(pool_state, 1.0)
    raised = pool.target * progress
    count = max(2, min(40, int(rnd.uniform(3, 28) * (0.4 + progress))))
    weights = [rnd.paretovariate(1.4) for _ in range(count)]
    scale = raised / sum(weights)
    start = pool.date_start
    last_day = today if pool_state == 'raising' else min(pool.date_deadline or today, today)
    span = max((last_day - start).days, 1)
    stakers = rnd.sample(list(people), min(count, len(people)))
    slot = 'overdue' if pool_state == 'default' else pool_state
    if showcase and my_left.get(slot, 0) > 0 and rnd.random() < 0.3 and pool.partner_id != showcase:
        my_left[slot] -= 1
        stakers[0] = showcase
    if pool.kind == 'rub':
        digits = lambda v: round(v, -2)  # noqa: E731
    else:
        digits = lambda v: _round(v, asset)  # noqa: E731
    rest = raised
    made = 0
    for index, partner in enumerate(stakers):
        last = index == len(stakers) - 1
        amount = digits(max(weights[index] * scale, pool.min_stake or 0))
        amount = digits(rest) if last else min(amount, digits(rest))
        if amount <= 0 or rest <= 0:
            break
        rest -= amount
        when = datetime.combine(start + timedelta(days=rnd.randint(0, span - 1)),
                                datetime.min.time()) + timedelta(hours=rnd.randint(8, 22),
                                                                 minutes=rnd.randint(0, 59))
        when = min(when, now - timedelta(minutes=5))
        tx = ('%064x' % rnd.getrandbits(256)) if pool.kind == 'coin' \
            else 'ПП-%06d' % rnd.randint(1000, 999999)
        vals = {'pool_id': pool.id, 'partner_id': partner.id, 'amount': amount, 'date': when,
                'tx_hash': tx}
        if pool_state == 'refunded' and partner != showcase and rnd.random() < 0.7:
            vals.update({'state': 'withdrawn',
                         'withdrawn_on': datetime.combine(pool.date_deadline, datetime.min.time())
                         + timedelta(days=rnd.randint(0, 6), hours=rnd.randint(9, 20))})
        Stake.create(vals)
        made += 1
    return made


def _make_payouts(pool, rnd, today, pool_state, periods, showcase):
    """Выплаты по графику: сумма за период — около потолка, делённого на
    число периодов до него, с разбросом выручки. Подтверждения: старше 14
    дней — получено (изредка молчанием или спор), свежие — ждут ответа."""
    if pool_state in ('raising', 'refunded') or not periods:
        return 0
    pool.invalidate_recordset(['tvl', 'paid_total'])
    cap = pool._cap_amount()
    to_cap = periods if pool_state == 'closed' else rnd.randint(max(periods + 2, 6), 24)
    made = 0
    for k in range(periods):
        when = pool.date_activated + timedelta(days=pool.payout_days * (k + 1) + rnd.randint(-3, 4))
        if when > today:
            break
        amount = cap / to_cap * rnd.uniform(0.55, 1.35)
        if pool_state == 'closed' and k == periods - 1 and rnd.random() < 0.75:
            pool.invalidate_recordset(['paid_total'])
            amount = max(cap - pool.paid_total, amount)
        revenue = amount / pool.revenue_share * 100
        if pool.kind == 'rub':
            revenue = round(revenue, -2)
            tx = 'ПП-%06d' % rnd.randint(1000, 999999)
        else:
            tx = '%064x' % rnd.getrandbits(256)
        recent = (today - when).days < CONFIRM_DAYS_DEMO
        pool.invalidate_recordset(['paid_total'])
        if pool.paid_total >= cap - 1e-9:
            break
        payout = pool._make_payout(revenue, when, tx)
        made += 1
        for line in payout.line_ids:
            roll = rnd.random()
            if recent:
                state = 'pending' if roll < 0.7 or line.partner_id == showcase else 'confirmed'
            else:
                state = 'confirmed' if roll < 0.8 else 'auto' if roll < 0.95 else 'disputed'
            vals = {'state': state}
            if state == 'confirmed':
                vals['confirmed_on'] = min(when + timedelta(days=rnd.randint(0, 13)), today)
            elif state == 'auto':
                vals['confirmed_on'] = min(when + timedelta(days=CONFIRM_DAYS_DEMO), today)
            elif state == 'disputed':
                vals['dispute_note'] = rnd.choice([
                    'Перевод не пришёл на кошелёк', 'Сумма меньше моей доли',
                    'Выручка за период занижена — прошу отчёт', 'Пришло на другой адрес'])
            line.write(vals)
        if pool.state == 'closed':
            break
    if pool_state == 'default':
        due = pool._next_due()
        pool.write({'state': 'default', 'date_default': due + timedelta(days=180) if due else today})
    elif pool_state == 'closed' and pool.state != 'closed':
        pool.write({'state': 'closed', 'date_end': min(pool.date_end or today, today)})
    return made


def _rebates(env):
    """Возвраты комиссии DEX за прошедшие месяцы с обменами: давние —
    выплачены, последний — начислен."""
    if 'coop.dex.rebate' not in env:
        return 0
    Rebate = env['coop.dex.rebate'].sudo()
    Trade = env['coop.crypto.trade'].sudo()
    first = Trade.search([('state', '=', 'done')], order='date asc', limit=1)
    if not first:
        return 0
    this_month = date.today().replace(day=1)
    cursor = first.date.date().replace(day=1)
    months = []
    while cursor < this_month:
        months.append(cursor)
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    made = 0
    for month in months:
        made += Rebate._rebate_month(month)
    if len(months) > 1:
        Rebate.search([('month', 'in', [m.strftime('%Y-%m') for m in months[:-1]])]).write(
            {'state': 'paid'})
    return made
