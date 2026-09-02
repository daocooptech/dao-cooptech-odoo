# -*- coding: utf-8 -*-
"""Кошельки участников и движения по ним.

Состав вкладок собирается сам по правилам платформы: фиатный, крипто,
взаимный кредит и токены — всем; паевой счёт — только членам
кооперативов, отдельный на каждый. Поэтому загрузчик не раскладывает
вкладки руками, а просит платформу собрать их и наполняет движениями то,
что получилось.

Суммы небольшие и разные: кошелёк, где у всех ровно по сто тысяч, ничего
не показывает — ни разброса, ни отрицательного сальдо, ни того, как
выглядит пустой счёт.
"""
import logging
import random

_logger = logging.getLogger(__name__)

# Крипто-активы, которые участники держат. Адрес — публичный и
# вымышленный: ключей платформа не хранит, и настоящих адресов в
# демонстрационных данных быть не должно.
ASSETS = ['RUBx', 'USDT', 'BTC', 'ETH', 'ERA']

FIAT_MOVEMENTS = [
    ('deal', 'Оплата по сделке'),
    ('deal', 'Поступление по сделке'),
    ('payout', 'Выплата по договору'),
    ('correction', 'Корректировка по акту сверки'),
]

LETS_MOVEMENTS = [
    ('offset', 'Взаимозачёт по кругу'),
    ('deal', 'Обязательство по сделке'),
    ('deal', 'Погашение встречным'),
]

SHARE_MOVEMENTS = [
    ('contribution', 'Вступительный взнос'),
    ('contribution', 'Паевой взнос'),
    ('contribution', 'Дополнительный паевой взнос'),
    ('payout', 'Кооперативная выплата'),
]


def load_wallets(env, target_partners=260):
    Wallet = env['coop.wallet'].sudo()
    Movement = env['coop.wallet.movement'].sudo()
    Partner = env['res.partner'].sudo()

    partners = Partner.search([('coop_is_participant', '=', True)], order='id')
    if not partners:
        _logger.warning('Нет участников — кошельки не наполняю')
        return

    # Администратор стенда — не участник каталога, и в выборку не попадает.
    # Но кошелёк он открывает первым, и пустые вкладки на первом же экране
    # выглядят как незаработавший раздел, а не как честный ноль.
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    if admin and admin.partner_id not in partners:
        partners = admin.partner_id | partners

    rnd = random.Random(20260902)
    wallets = movements = 0

    for index, partner in enumerate(partners[:target_partners]):
        Wallet.sync_for_partner(partner)
        own = Wallet.search([('partner_id', '=', partner.id)])
        wallets += len(own)

        for wallet in own:
            if wallet.movement_ids:
                continue
            if wallet.kind == 'crypto':
                # У крипто-кошелька движений здесь нет: они происходят в
                # сети, а не на платформе. Заполняем актив и адрес.
                wallet.write({
                    'asset_code': ASSETS[index % len(ASSETS)],
                    'address': '0x%036x' % (index * 7919 + 13),
                })
                continue
            if wallet.kind == 'token':
                continue

            movements += _fill(Movement, wallet, rnd, index)

    _logger.info('Кошельки: вкладок %s, движений %s', wallets, movements)


def _fill(Movement, wallet, rnd, index):
    """Наполнить вкладку движениями.

    Каждый десятый кошелёк остаётся пустым намеренно: пустой счёт —
    обычное состояние у новичка, и экран для него должен быть проверен.
    """
    if index % 10 == 3:
        return 0

    if wallet.kind == 'fiat':
        source, scale = FIAT_MOVEMENTS, (3000, 180000)
    elif wallet.kind == 'lets':
        source, scale = LETS_MOVEMENTS, (500, 40000)
    else:
        source, scale = SHARE_MOVEMENTS, (1000, 90000)

    count = rnd.choice([1, 2, 2, 3, 4, 5])
    created = 0
    for offset in range(count):
        kind, name = source[(index + offset) % len(source)]
        value = rnd.randint(*scale)
        # Направление зависит от основания: взнос и оплата уходят,
        # поступление и выплата приходят. Знак и есть направление.
        outgoing = kind in ('contribution',) or 'Оплата' in name or 'Обязательство' in name
        Movement.create({
            'wallet_id': wallet.id,
            'date': '20%02d-%02d-%02d' % (
                24 + ((index + offset) % 3), 1 + (offset % 12),
                1 + ((index + offset) % 27)),
            'name': name,
            'kind': kind,
            'amount': -value if outgoing else value,
            'state': 'draft' if (index + offset) % 17 == 5 else 'confirmed',
        })
        created += 1
    return created
