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
from datetime import timedelta

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


# Алфавиты адресов: bech32 у биткоина и своей сети, base58 у Соланы,
# base64url у TON. Шестнадцатеричный хвост у всех подряд выдавал подделку
# с первого взгляда — тем более что короткое число давало в нём сплошные
# нули: «bc1q0000…».
_BECH32 = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
_BASE58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
_BASE64URL = ('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
              '0123456789-_')


def _address_for(code, seed):
    """Вымышленный публичный адрес, похожий на настоящий.

    Настоящих адресов в демонстрационных данных быть не должно: на них
    можно случайно отправить деньги. Поэтому адрес собран из случайных
    знаков алфавита сети — формат и длина настоящие, контрольная сумма
    нет, и кошелёк такой адрес не примет.

    Жребий — от кошелька и сети, а не общий: адрес не меняется от
    прогона к прогону (встроенный `hash` строки меняется).
    """
    rnd = random.Random('%s:%s' % (code, seed))

    def pick(alphabet, n):
        return ''.join(rnd.choice(alphabet) for _ in range(n))

    if code == 'btc':
        return 'bc1q' + pick(_BECH32, 38)
    if code == 'koop':
        return 'koop1' + pick(_BECH32, 38)
    if code == 'ton':
        # Адрес для людей: «UQ» — кошелёк без возврата при ошибке.
        # Третий знак — от байта рабочей цепочки: у основной это «A»–«D».
        return 'UQ' + pick('ABCD', 1) + pick(_BASE64URL, 45)
    if code == 'sol':
        return pick(_BASE58[1:], 1) + pick(_BASE58, rnd.choice([42, 43]))
    return '0x' + pick('0123456789abcdef', 40)


def tx_hash_for(code, seed):
    """Вымышленный хеш операции в формате своей сети (решение 416).

    Раньше хеши были вида «eth_000…07» — видно, что заглушка. Теперь как
    у настоящих: BTC и сеть платформы — 64 шестнадцатеричных знака, ETH и
    совместимые — то же с «0x», TON — base64, Solana — подпись base58.
    Знаки случайные — настоящей операции с таким хешем нет. Жребий — от
    сети и номера, чтобы хеш не менялся от прогона к прогону.
    """
    rnd = random.Random('tx:%s:%s' % (code, seed))

    def pick(alphabet, n):
        return ''.join(rnd.choice(alphabet) for _ in range(n))

    if code in ('btc', 'koop'):
        return pick('0123456789abcdef', 64)
    if code == 'ton':
        return pick(_BASE64URL, 43) + '='
    if code == 'sol':
        return pick(_BASE58[1:], rnd.choice([87, 88]))
    return '0x' + pick('0123456789abcdef', 64)


def repair_tx_hashes(env):
    """Переписать хеши операций-заглушки «код_000…» на правдоподобные.
    Повторный запуск ничего не меняет: заглушек не остаётся."""
    if 'coop.wallet.tx' not in env:
        return 0
    Tx = env['coop.wallet.tx'].sudo()
    stubs = Tx.search([('tx_hash', '=like', r'%\_00000%')])
    for tx in stubs:
        code = (tx.tx_hash or '').split('_', 1)[0] or (tx.network_id.code or '')
        tx.tx_hash = tx_hash_for(code, tx.id)
    if stubs:
        _logger.info('Кошельки: хеши операций переписаны у %s', len(stubs))
    return len(stubs)


def repair_addresses(env):
    """Переписать адреса, заведённые прежним способом.

    Прежние адреса узнаются по хвосту из нулей; у настоящего адреса
    такого не бывает, и адреса, внесённые людьми, этим не задеваются.
    Загрузчик адресов у уже наполненного кошелька не трогает, поэтому
    без этого прохода нули остались бы на боевой навсегда.
    """
    if 'coop.wallet.address' not in env:
        return 0
    stale = env['coop.wallet.address'].sudo().with_context(
        active_test=False).search([('address', 'like', '%00000000%')])
    fixed = 0
    for address in stale:
        code = address.network_id.code
        if not code:
            continue
        address.address = _address_for(code, address.wallet_id.id)
        fixed += 1
    if fixed:
        _logger.info('Кошельки: переписано адресов из нулей — %s', fixed)
    return fixed


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


# ── История кошелька главного участника витрины ─────────────────────────
#
# Владелец 27.09.2026: «историю операций сделай 200». У главного участника
# было 11 движений за три года, и дашборд «Мои деньги» на нём выглядел
# пустым: три столбца за год и таблица на четыре строки. Здесь история
# доводится до двухсот: пополнения и выводы своими способами оплаты,
# расчёты по его настоящим сделкам, переводы участникам и от них, редкие
# корректировки — с разбросом по месяцам, суммам и состояниям.

# Кто в сделке получает деньги, а кто платит — по роли участника.
ROLE_RECEIVES = {'продавец', 'исполнитель', 'владелец склада', 'кредитор', 'передаёт'}
ROLE_PAYS = {'покупатель', 'арендатор', 'размещающий', 'заказчик', 'заёмщик', 'получает'}

CORRECTIONS = [
    ('Возврат комиссии банка за перевод', 1),
    ('Корректировка: двойное списание по карте', 1),
    ('Удержана комиссия за срочный вывод', -1),
    ('Возврат ошибочного зачисления', -1),
]

HISTORY_KINDS = (['topup'] * 27 + ['withdraw'] * 24 + ['transfer_out'] * 22
                 + ['transfer_in'] * 22 + ['correction'] * 3)


def _method_from(method):
    """«с карты МИР •• 4412», «через СБП: +7-…», «с расчётного счёта •• 7741»."""
    short = method.label.split('(')[0].strip()
    if method.kind == 'sbp':
        return 'через ' + short
    if method.kind == 'account':
        return 'с расчётного счёта ' + short.replace('Расчётный счёт', '').strip()
    return 'с карты ' + short.replace('Карта', '').strip()


def _method_to(method):
    short = method.label.split('(')[0].strip()
    if method.kind == 'sbp':
        return 'по ' + short
    if method.kind == 'account':
        return 'на расчётный счёт ' + short.replace('Расчётный счёт', '').strip()
    return 'на карту ' + short.replace('Карта', '').strip()


def fill_main_history(env, login='dashkevich', target=200):
    """Довести историю кошелька главного участника до `target` движений.

    Прогон один: набралось — выходит. Остаток ведётся по ходу времени и в
    минус не уходит: расход, на который денег нет, становится меньше или
    превращается в пополнение, а перед старым крупным списанием, которое
    уже было в истории, ставится пополнение.
    """
    user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    if not user:
        return 0
    partner = user.partner_id
    # Без записей в ленте: двести движений завели бы двести сообщений.
    Movement = env['coop.wallet.movement'].sudo().with_context(
        tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    wallet = env['coop.wallet'].sudo().wallet_for(partner)
    have = Movement.search_count([('wallet_id', '=', wallet.id)])
    if have >= target:
        return 0
    if not wallet.method_ids:
        _fill_methods(env, wallet, 0)
    methods = wallet.method_ids
    default = methods.filtered('is_default')[:1] or methods[:1]

    rnd = random.Random('main-history:%s' % partner.id)
    today = fields.Date.context_today(wallet)
    start = fields.Date.to_date('2024-01-08')
    span = (today - start).days

    deals = env['coop.deal'].sudo().search([
        '|', ('party_a_id', '=', partner.id), ('party_b_id', '=', partner.id),
        ('amount', '>', 0), ('state', 'not in', ('draft', 'cancelled'))])
    people = env['res.partner'].sudo().search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('id', '!=', partner.id)], order='id', limit=80)

    # (дата, вид, сумма со знаком, название, способ, контрагент, сделка)
    plan = []

    # Расчёты по настоящим сделкам — частями, от даты сделки.
    for deal in deals:
        mine_a = deal.party_a_id == partner
        role = ((deal.role_a if mine_a else deal.role_b) or '').strip().lower()
        other = deal.party_b_id if mine_a else deal.party_a_id
        if role in ROLE_RECEIVES:
            sign = 1
        elif role in ROLE_PAYS:
            sign = -1
        else:
            sign = 1 if deal.id % 2 else -1
        parts = 1 if deal.amount < 20000 else rnd.choice([2, 2, 3])
        paid = deal.amount if deal.state == 'done' else deal.amount * rnd.choice([0.3, 0.5])
        begin = deal.signed_on or today
        for step in range(parts):
            when = begin + timedelta(days=3 + step * rnd.randint(12, 30))
            if when > today:
                # Срок этой части ещё не пришёл — она не проведена.
                break
            title = ('Поступление по сделке %s — %s' if sign > 0
                     else 'Оплата по сделке %s — %s') % (deal.number, other.name)
            plan.append((when, 'deal', sign * round(paid / parts), title, False, other, deal))

    # Остальное — пополнения, выводы, переводы, корректировки. Ближе к
    # сегодняшнему дню гуще: платформой пользуются всё больше.
    for n in range(max(0, target - have - len(plan))):
        when = start + timedelta(days=int(span * (rnd.random() ** 0.6)))
        kind = rnd.choice(HISTORY_KINDS)
        method = methods[n % len(methods)]
        if kind == 'topup':
            amount = rnd.choice([3000, 5000, 10000, 15000, 20000, 30000, 50000]) + rnd.randint(0, 9) * 100
            plan.append((when, 'topup', amount, 'Пополнение ' + _method_from(method), method, False, False))
        elif kind == 'withdraw':
            plan.append((when, 'withdraw', -rnd.randint(20, 400) * 100,
                         'Вывод ' + _method_to(method), method, False, False))
        elif kind in ('transfer_out', 'transfer_in'):
            who = people[rnd.randrange(len(people))]
            amount = rnd.choice([500, 800, 1200, 1500, 2500, 3000, 5000, 7500, 12000])
            if kind == 'transfer_out':
                plan.append((when, 'transfer', -amount, 'Перевод участнику — ' + who.name, False, who, False))
            else:
                plan.append((when, 'transfer', amount, 'Перевод от участника — ' + who.name, False, who, False))
        else:
            title, sign = CORRECTIONS[n % len(CORRECTIONS)]
            plan.append((when, 'correction', sign * rnd.randint(1, 30) * 50, title, False, False, False))
    plan.sort(key=lambda row: row[0])

    old = [(m.date, m.amount) for m in Movement.search(
        [('wallet_id', '=', wallet.id), ('state', '=', 'confirmed')], order='date, id')]
    floor, balance, oi, created = 2000.0, 0.0, 0, 0

    def topup(when, amount):
        Movement.create({
            'wallet_id': wallet.id, 'date': when, 'kind': 'topup', 'method_id': default.id,
            'name': 'Пополнение ' + _method_from(default), 'amount': amount, 'state': 'confirmed'})

    for when, kind, value, title, method, other, deal in plan:
        # Сначала — то, что уже было в истории к этой дате.
        while oi < len(old) and old[oi][0] <= when:
            odate, oamount = old[oi]
            if balance + oamount < floor and have + created < target:
                need = floor - (balance + oamount) + rnd.randint(5, 40) * 1000
                topup(odate - timedelta(days=rnd.randint(1, 4)), need)
                balance += need
                created += 1
            balance += oamount
            oi += 1
        if have + created >= target:
            break
        # Деньги на кошельке не копятся без конца: при большом остатке
        # выводят крупнее и пополняют реже (первый прогон на копии дал
        # к концу 715 тысяч против нынешних 117).
        if have + created == target - 1:
            # Последняя — сегодняшний вывод, ещё в работе: состояние «деньги
            # в пути» должно быть видно, а жребий его может и не дать.
            when, kind, method, other, deal = today, 'withdraw', default, False, False
            value = -max(1000, round(min(15000, balance * 0.2) / 100) * 100)
            title = 'Вывод ' + _method_to(default)
        elif kind == 'withdraw' and balance > 150000:
            value = -round(balance * rnd.uniform(0.25, 0.55) / 100) * 100
        elif kind == 'topup' and balance > 250000:
            value = max(1000, round(value * 0.3 / 100) * 100)
        if value < 0 and balance + value < floor:
            if balance - floor < 1000:
                # Денег нет — расхода не было, было пополнение.
                if kind != 'deal':
                    kind, method, other = 'topup', method or default, False
                    title = 'Пополнение ' + _method_from(method)
                value = abs(value)
            else:
                value = -max(500, round((balance - floor) * rnd.uniform(0.4, 0.9) / 100) * 100)
        # Состояния: свежие выводы и пополнения ещё в работе, часть выводов
        # банк отклонил, часть переводов участник отменил сам.
        age = (today - when).days
        state = 'confirmed'
        if kind in ('withdraw', 'topup') and age < 8:
            state = 'pending'
        elif kind == 'withdraw' and created % 17 == 5:
            state = 'failed'
        elif kind == 'transfer' and value < 0 and created % 23 == 11:
            state = 'cancelled'
        Movement.create({
            'wallet_id': wallet.id,
            'date': when,
            'name': title,
            'kind': kind,
            'method_id': method.id if (method and kind in ('topup', 'withdraw')) else False,
            'counterparty_id': other.id if other else False,
            'deal_id': deal.id if deal else False,
            'amount': value,
            'state': state,
        })
        if state == 'confirmed':
            balance += value
        created += 1
    _logger.info('Кошелёк главного участника %s: добавлено движений %s, остаток %.0f',
                 login, created, balance)
    return created
