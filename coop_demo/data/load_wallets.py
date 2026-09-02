# -*- coding: utf-8 -*-
"""Кошельки участников: активы в сетях, способы оплаты, линии взаимного
кредита и паевые счета.

Наполняется по-настоящему, а не по три строки на вкладку: на четырёх
записях не видно ни сортировки, ни страниц, ни того, как ведёт себя
таблица под нагрузкой. И не видно состояний — пустого кошелька у
новичка, отклонённого банком вывода, неподтверждённой операции по
взаимному кредиту, круга долгов, ждущего третьей подписи.
"""
import logging
import random

from odoo import fields

_logger = logging.getLogger(__name__)

# Активы по сетям — как в макете: у сети своя монета, плюс токены
# стандарта поверх неё.
ASSETS = [
    ('btc', 'Bitcoin', 'BTC', '', 0.0004, 0.09, 7_270_000),
    ('eth', 'Ethereum', 'ETH', '', 0.02, 3.4, 221_000),
    ('eth', 'Tether USD', 'USDT', 'ERC-20', 40, 1800, 90),
    ('bnb', 'BNB', 'BNB', '', 0.3, 6.5, 54_400),
    ('ton', 'Toncoin', 'TON', '', 15, 700, 330),
    ('sol', 'Solana', 'SOL', '', 0.8, 26, 9_000),
    ('koop', 'КООП', 'КООП', 'нативный токен сети кооператива', 200, 9000, 10),
]

METHODS = [
    ('card', 'Карта МИР •• 4412 (Сбербанк)'),
    ('card', 'Карта МИР •• 8830 (Т-Банк)'),
    ('sbp', 'СБП: +7-928-233-23-24'),
    ('sbp', 'СБП: +7-903-118-77-05'),
    ('account', 'Расчётный счёт •• 7741'),
]

FIAT_OPERATIONS = [
    ('topup', 'Пополнение с карты', 1),
    ('withdraw', 'Вывод на карту', -1),
    ('deal', 'Оплата по сделке', -1),
    ('deal', 'Поступление по сделке', 1),
    ('transfer', 'Перевод участнику', -1),
]

CREDIT_OPERATIONS = [
    ('Помощь с монтажом каркаса теплицы, 3 часа', 15),
    ('Получили пельмени домашней лепки, 5 кг', -25),
    ('Консультация по электромонтажу, 2 часа', 10),
    ('Получили мёд натуральный, 1 кг', -18),
    ('Погрузочные работы, смена', 8),
    ('Забрали доски обрезные, куб', -12),
    ('Ремонт мотоблока', 6),
    ('Взяли саженцы яблони, 20 шт.', -9),
]

SHARE_MOVES = [
    ('entry', 'Вступительный паевой взнос', 'Протокол общего собрания № %s', 1),
    ('share', 'Паевой взнос', 'Протокол правления № %s', 1),
    ('extra', 'Дополнительный паевой взнос', 'Заявление участника', 1),
    ('accrual', 'Кооперативная выплата по итогам года', 'Протокол общего собрания № %s', 1),
    ('payout', 'Выплата на руки по заявлению', 'Заявление участника', -1),
]

CHARTER_NOTES = [
    'Выплата начисляется за участие в работе — смены и оборот через '
    'кооператив, а не размер пая. При выходе пай возвращается в течение '
    'года после утверждения годового отчёта; неделимый фонд разделу не '
    'подлежит.',
    'Выплата начисляется пропорционально закупкам через кооператив за год. '
    'Выплаты на руки не производятся до трёх лет членства — начисленное '
    'остаётся в паю.',
    'Начисление считается от выработки пропорционально доле пая: здесь '
    'вклад измеряется вложением, а не трудом.',
]


def load_wallets(env, target=200):
    Wallet = env['coop.wallet'].sudo()
    Partner = env['res.partner'].sudo()
    Network = env['coop.wallet.network'].sudo()

    partners = Partner.search([('coop_is_participant', '=', True)], order='id')
    if not partners:
        _logger.warning('Нет участников — кошельки не наполняю')
        return

    # Администратор стенда — не участник каталога и в выборку не попадает.
    # Но кошелёк он открывает первым, и пустые вкладки на первом же экране
    # читаются как незаработавший раздел, а не как честный ноль.
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    if admin and admin.partner_id not in partners:
        partners = admin.partner_id | partners

    networks = {n.code: n for n in Network.with_context(active_test=False).search([])}
    if not networks:
        _logger.warning('Справочник сетей пуст — крипто-вкладку не наполняю')

    rnd = random.Random(20260902)
    made = {'wallets': 0, 'assets': 0, 'methods': 0, 'moves': 0,
            'lines': 0, 'credits': 0, 'shares': 0, 'share_moves': 0}

    for index, partner in enumerate(partners[:target]):
        wallet = Wallet.wallet_for(partner)
        made['wallets'] += 1

        # Каждый десятый — новичок: ни активов, ни карт, ни истории.
        # Пустой кошелёк надо на чём-то проверять.
        newcomer = index % 10 == 3

        if not newcomer and networks:
            made['assets'] += _fill_crypto(env, wallet, networks, rnd, index)
            made['methods'] += _fill_methods(env, wallet, index)
            made['moves'] += _fill_fiat(env, wallet, rnd, index)
        made['share_moves'] += _fill_shares(env, wallet, rnd, index)

    lines, credits = _fill_credit(env, partners[:target], rnd)
    made['lines'], made['credits'] = lines, credits
    _propose_clearing(env, rnd)

    _logger.info(
        'Кошельки: %(wallets)s, активов %(assets)s, способов оплаты %(methods)s, '
        'движений %(moves)s, линий кредита %(lines)s, операций по ним %(credits)s, '
        'движений по паю %(share_moves)s', made)


def _fill_crypto(env, wallet, networks, rnd, index):
    Asset = env['coop.wallet.asset'].sudo()
    Address = env['coop.wallet.address'].sudo()
    if wallet.asset_ids:
        return 0

    chosen = rnd.sample(ASSETS, rnd.choice([2, 3, 4, 5, 7]))
    created = 0
    used_networks = set()
    now = fields.Datetime.now()
    for code, name, symbol, standard, low, high, rate in chosen:
        network = networks.get(code)
        if not network:
            continue
        quantity = round(rnd.uniform(low, high), 8)
        Asset.create({
            'wallet_id': wallet.id,
            'network_id': network.id,
            'name': name,
            'symbol': symbol,
            'standard': standard,
            'quantity': quantity,
            'valuation': round(quantity * rate),
            'valued_at': now,
            'valuation_source': 'Средневзвешенный курс бирж',
            'balance_at': now,
        })
        created += 1
        used_networks.add(code)

    for code in used_networks:
        network = networks[code]
        Address.create({
            'wallet_id': wallet.id,
            'network_id': network.id,
            'address': _address_for(code, wallet.id),
        })

    # У части кошельков сеть «не отвечает»: состояние устаревших данных
    # должно быть на чём проверить.
    wallet.write({
        'crypto_synced_at': now,
        'crypto_sync_failed': index % 13 == 6,
    })
    return created


def _address_for(code, seed):
    """Вымышленный публичный адрес, похожий на настоящий.

    Настоящих адресов в демонстрационных данных быть не должно: на них
    можно случайно отправить деньги.
    """
    tail = '%040x' % (seed * 7919 + hash(code) % 100000)
    if code == 'btc':
        return 'bc1q' + tail[:38]
    if code == 'ton':
        return 'EQ' + tail[:46]
    if code == 'sol':
        return tail[:44]
    if code == 'koop':
        return 'koop1' + tail[:38]
    return '0x' + tail[:40]


def _fill_methods(env, wallet, index):
    Method = env['coop.wallet.method'].sudo()
    if wallet.method_ids:
        return 0
    count = 1 + (index % 3)
    created = 0
    for offset in range(count):
        kind, label = METHODS[(index + offset) % len(METHODS)]
        Method.create({
            'wallet_id': wallet.id,
            'kind': kind,
            'label': label,
            'sequence': (offset + 1) * 10,
            'is_default': offset == 0,
        })
        created += 1
    return created


def _fill_fiat(env, wallet, rnd, index):
    Movement = env['coop.wallet.movement'].sudo()
    if wallet.movement_ids:
        return 0
    methods = wallet.method_ids
    count = rnd.choice([2, 3, 4, 5, 6, 8])
    created = 0
    for offset in range(count):
        kind, title, sign = FIAT_OPERATIONS[(index + offset) % len(FIAT_OPERATIONS)]
        method = methods[offset % len(methods)] if methods else False
        name = title
        if kind in ('topup', 'withdraw') and method:
            name = '%s %s' % (title, method.label.split('(')[0].strip())
        # Отклонённый банком вывод и операция «в работе» — обычные
        # состояния, и без них экран показывал бы только свершившееся.
        state = 'confirmed'
        if (index + offset) % 23 == 7:
            state = 'failed'
        elif (index + offset) % 19 == 4:
            state = 'pending'
        Movement.create({
            'wallet_id': wallet.id,
            'date': '20%02d-%02d-%02d' % (
                24 + ((index + offset) % 3), 1 + (offset % 12),
                1 + ((index + offset) % 27)),
            'name': name,
            'kind': kind,
            'method_id': method.id if (method and kind in ('topup', 'withdraw')) else False,
            'amount': sign * rnd.randint(2000, 90000),
            'state': state,
        })
        created += 1
    return created


def _fill_shares(env, wallet, rnd, index):
    Move = env['coop.share.move'].sudo()
    created = 0
    for offset, account in enumerate(wallet.share_account_ids):
        if account.move_ids:
            continue
        if not account.charter_note:
            account.charter_note = CHARTER_NOTES[(index + offset) % len(CHARTER_NOTES)]
        count = rnd.choice([2, 2, 3, 4])
        for step in range(count):
            kind, title, basis, sign = SHARE_MOVES[step % len(SHARE_MOVES)]
            if '%s' in basis:
                basis = basis % (1 + ((index + step) % 20))
            amount = sign * rnd.choice([12000, 30000, 50000, 60000, 100000])
            if kind == 'accrual':
                amount = rnd.randint(3000, 22000)
            if kind == 'payout':
                amount = -rnd.randint(2000, 12000)
            Move.create({
                'account_id': account.id,
                'date': '20%02d-%02d-%02d' % (
                    23 + ((index + step) % 4), 1 + (step % 12),
                    1 + ((index + step) % 27)),
                'name': title,
                'kind': kind,
                'basis': basis,
                'amount': amount,
                'state': 'confirmed',
            })
            created += 1
    return created


def _fill_credit(env, partners, rnd):
    """Линии взаимного кредита между парами участников.

    Пары берутся не случайно, а по кругу: так среди них наверняка
    окажется замкнутое кольцо долгов, и вкладку взаимозачёта будет на чём
    проверить.
    """
    Line = env['coop.credit.line'].sudo()
    Movement = env['coop.credit.movement'].sudo()
    people = [p for p in partners if not p.is_company]
    if len(people) < 3:
        return 0, 0

    lines = credits = 0
    for index in range(min(120, len(people))):
        first = people[index]
        second = people[(index * 7 + 3) % len(people)]
        if first == second:
            continue
        line = Line.line_for(first, second)
        if line.movement_ids:
            continue
        lines += 1
        line.write({
            'limit_by_partner': rnd.choice([50, 100, 100, 200]),
            'limit_by_counterparty': rnd.choice([50, 100, 100, 200]),
        })
        for offset in range(rnd.choice([1, 2, 2, 3])):
            title, amount = CREDIT_OPERATIONS[(index + offset) % len(CREDIT_OPERATIONS)]
            # Часть операций ждёт подтверждения второй стороны — это
            # обычное состояние, и оно должно быть видно.
            state = 'proposed' if (index + offset) % 9 == 4 else 'confirmed'
            Movement.create({
                'line_id': line.id,
                'date': '20%02d-%02d-%02d' % (
                    25 + ((index + offset) % 2), 1 + (offset % 12),
                    1 + ((index + offset) % 27)),
                'name': title,
                'amount': amount,
                'state': state,
                'proposed_by_id': first.id,
                'confirmed_by_id': second.id if state == 'confirmed' else False,
            })
            credits += 1
    return lines, credits


def _propose_clearing(env, rnd):
    """Предложить один круг взаимозачёта, ждущий подписей.

    Один, а не десять: круг — событие редкое, и десяток одновременно
    предложенных кругов выглядел бы как ошибка, а не как данные.
    """
    Clearing = env['coop.credit.clearing'].sudo()
    Signature = env['coop.credit.signature'].sudo()
    Line = env['coop.credit.line'].sudo()
    if Clearing.search_count([]):
        return

    debts = Line.search([('balance', '<', 0)], limit=3)
    if len(debts) < 3:
        return
    participants = debts.mapped('partner_id') | debts.mapped('counterparty_id')
    amount = min(abs(line.balance) for line in debts)
    clearing = Clearing.create({
        'name': 'Круг взаимных долгов',
        'amount': amount,
        'participant_ids': [(6, 0, participants.ids)],
        'line_ids': [(6, 0, debts.ids)],
    })
    for offset, partner in enumerate(participants):
        Signature.create({
            'clearing_id': clearing.id,
            'partner_id': partner.id,
            # Двое подписали, третий ещё нет: правило «не подписал один —
            # раунд отменяется целиком» проверяется именно на этом.
            'signed': offset < len(participants) - 1,
            'signed_on': fields.Date.context_today(clearing) if offset < len(participants) - 1 else False,
        })
