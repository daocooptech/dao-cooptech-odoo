# -*- coding: utf-8 -*-
"""Виды пая в портфеле (решение 512): дивиденды по дополнительному паю,
приращённый пай со сроком погашения, сбережения в КПК.

Пай за помещение размечается сам — по форме кооператива (ЖСК, ЖК, ГСК).
Прогон повторяемый: у счёта, где вид уже заведён, ничего не добавляется.
"""
import logging
import random
from datetime import date

_logger = logging.getLogger(__name__)

TRADE_FORMS = ('po', 'pk', 'artel', 'spk', 'sppk', 'union', 'fprok')
SAVINGS_FORMS = ('kpk', 'skpk')


def _room(env, account, year, amount):
    """Сколько можно начислить за год в пределах лимита кооперативных выплат."""
    if 'coop.tax.payout.limit' not in env:
        return amount
    limit = env['coop.tax.payout.limit'].sudo().search([
        ('cooperative_id', '=', account.cooperative_id.id), ('year', '=', year)], limit=1)
    if not limit:
        return amount
    limit.invalidate_recordset(['accrued', 'remaining'])
    return min(amount, int(limit.remaining))


def _early_extra(Move, account):
    """Главному участнику — дополнительный взнос закрытого года, чтобы в
    портфеле была видна строка дивидендов: все его доп. взносы — 2026 года."""
    joined = account.joined_on
    if not joined or joined.year > 2025 or account.move_ids.filtered(
            lambda m: m.kind == 'extra' and m.date.year < 2026):
        return
    year = max(joined.year, 2024)
    Move.create({
        'account_id': account.id, 'date': date(year, 6, 3), 'name': 'Дополнительный паевой взнос',
        'kind': 'extra', 'amount': 20000, 'state': 'confirmed',
        'basis': 'Заявление пайщика, решение правления № %d' % (1 + account.id % 12),
    })


def _dividends(env, Move, account, rnd, main):
    if main:
        _early_extra(Move, account)
    extra = account.move_ids.filtered(lambda m: m.kind == 'extra' and m.state == 'confirmed')
    if not extra or account.move_ids.filtered(
            lambda m: m.share_kind == 'extra' and m.kind == 'accrual'):
        return 0
    if not main and rnd.random() > 0.7:
        return 0
    first = min(extra.mapped('date')).year
    created = 0
    for year in range(max(first, 2023), 2026):
        rate = rnd.choice([0.04, 0.05, 0.06, 0.07, 0.08])
        base = sum(extra.filtered(lambda m: m.date.year <= year).mapped('amount'))
        amount = _room(env, account, year, int(base * rate))
        if amount < 300:
            continue
        # Год без решения собрания о дивидендах — тоже факт.
        if not main and rnd.random() < 0.2:
            continue
        Move.create({
            'account_id': account.id, 'date': date(year + 1, 4, 10 + year % 15),
            'name': 'Дивиденды по дополнительному паю за %d год' % year,
            'kind': 'accrual', 'share_kind': 'extra', 'amount': amount,
            'basis': 'Протокол общего собрания № %d' % (2 + (account.id + year) % 9),
            'state': 'confirmed' if year < 2025 or rnd.random() < 0.8 else 'requested',
        })
        created += 1
    return created


def _increment(env, Move, account, rnd, main):
    if account.move_ids.filtered(lambda m: m.share_kind == 'increment'):
        return 0
    if not main and rnd.random() > 0.4:
        return 0
    created = 0
    for year in rnd.sample([2023, 2024, 2025], rnd.choice([1, 1, 2])):
        amount = _room(env, account, year, rnd.randint(4, 30) * 500)
        if amount < 500:
            continue
        # Срок погашения назначает собрание; у части — ещё не назначен.
        redeem = date(year + rnd.choice([3, 4, 5]), 1, 1) if main or rnd.random() < 0.85 else False
        Move.create({
            'account_id': account.id, 'date': date(year + 1, 5, 5 + year % 20),
            'name': 'Приращение пая по итогам %d года' % year,
            'kind': 'accrual', 'share_kind': 'increment', 'amount': amount,
            'redeem_from': redeem,
            'basis': 'Протокол общего собрания № %d' % (3 + (account.id + year) % 8),
            'state': 'confirmed',
        })
        created += 1
    return created


def _savings(Move, account, rnd, main):
    if account.move_ids.filtered(lambda m: m.share_kind == 'savings'):
        return 0
    if not main and rnd.random() > 0.85:
        return 0
    number = 100 + account.id
    basis = 'Договор передачи личных сбережений № %d' % number
    principal = rnd.choice([50000, 100000, 150000, 200000, 300000, 500000])
    start = date(rnd.choice([2023, 2024, 2025]), rnd.randint(1, 12), rnd.randint(1, 27))
    rows = [{'date': start, 'name': 'Передача личных сбережений', 'kind': 'savings_in',
             'amount': principal, 'state': 'confirmed'}]
    rate = rnd.choice([0.08, 0.09, 0.10, 0.11, 0.12])
    for year in range(start.year, 2026):
        months = 12 - start.month if year == start.year else 12
        amount = int(principal * rate * months / 12)
        if amount >= 100:
            rows.append({'date': date(year + 1, 1, 15), 'name': 'Компенсация за сбережения за %d год' % year,
                         'kind': 'savings_interest', 'amount': amount, 'state': 'confirmed'})
    roll = rnd.random()
    if not main and roll < 0.2:
        # Договор закончился: сбережения возвращены целиком.
        total = sum(r['amount'] for r in rows)
        rows.append({'date': date(2026, rnd.randint(2, 10), 20), 'name': 'Возврат сбережений по окончании договора',
                     'kind': 'savings_out', 'amount': -total, 'state': 'confirmed'})
    elif roll < 0.4:
        rows.append({'date': date(2026, rnd.randint(3, 11), 12), 'name': 'Частичный возврат сбережений',
                     'kind': 'savings_out', 'amount': -principal // 4,
                     'state': rnd.choice(['confirmed', 'requested', 'declined'])})
    for row in rows:
        Move.create(dict(row, account_id=account.id, basis=basis))
    return len(rows)


def load_share_kinds(env, login='dashkevich'):
    if 'coop.share.move' not in env or 'share_kind' not in env['coop.share.move']._fields:
        return 0
    Move = env['coop.share.move'].sudo().with_context(tracking_disable=True)
    user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    accounts = env['coop.share.account'].sudo().search([('state', '!=', 'closed')], order='id')
    created = 0
    for account in accounts:
        rnd = random.Random(20261127 + account.id)
        main = bool(user) and account.partner_id == user.partner_id
        form = account.cooperative_id.coop_legal_form_id.code
        if form in SAVINGS_FORMS:
            created += _savings(Move, account, rnd, main)
        elif form in TRADE_FORMS:
            created += _dividends(env, Move, account, rnd, main)
            created += _increment(env, Move, account, rnd, main)
    _logger.info('Виды пая: заведено %s движений', created)
    return created
