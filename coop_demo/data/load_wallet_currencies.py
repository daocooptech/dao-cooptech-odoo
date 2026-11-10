# -*- coding: utf-8 -*-
"""Валюты, счета и операции фиатного кошелька в демо (задача 400). Идемпотентно.

Кошелёк под dashkevich — богатый: двенадцать валют, чтобы проверять
переключатель, в том числе рубль с цифровым рублём. У остальных участников
разные формы: только рубли; рубль, юань и цифровой рубль; двойное
гражданство РФ и Казахстана с RUB, KZT, EUR; валюта, у которой ЦБ не
публикует курс (MYR); валюта с устаревшим курсом (UGX). Суммы — в масштабе
валюты: рублёвая сумма делится на курс.

Курсы берутся у ЦБ РФ; когда сети нет, ставятся ориентировочные вручную
(источник «Вручную»): экран без курсов показывал бы только пустое «Все».
Названия банков вымышленные — вопрос «реальные или вымышленные» открыт.
"""
import random
from datetime import date, timedelta

# Ориентировочно, рублей за единицу, — только когда ЦБ недоступен.
FALLBACK_RATES = {
    'USD': 80.0, 'EUR': 92.0, 'CNY': 11.0, 'KZT': 0.16, 'INR': 0.95,
    'AED': 21.8, 'BYN': 27.0, 'UZS': 0.0065, 'AMD': 0.21, 'THB': 2.3,
    'VND': 0.0032, 'BRL': 15.0, 'KGS': 0.92, 'TJS': 7.5, 'AZN': 47.0,
    'TMT': 22.8, 'ZAR': 4.4, 'EGP': 1.6, 'ETB': 0.6, 'IDR': 0.005,
    'IRR': 0.0002, 'CUP': 3.3, 'BOB': 11.6, 'NGN': 0.05,
}
BANKS = ['Северный банк', 'Торговый союз', 'Кооперативный банк', 'Речной банк',
         'Народный банк', 'Столичный банк']
# Валюты кошелька dashkevich — двенадцать, считая рубль.
RICH = ['RUB', 'CNY', 'EUR', 'USD', 'KZT', 'INR', 'AED', 'BYN', 'UZS', 'AMD',
        'THB', 'VND']
TITLES = [
    ('topup', 'Пополнение цифровым рублём'), ('withdraw', 'Вывод на счёт'),
    ('transfer', 'Перевод участнику'), ('deal', 'Оплата по сделке'),
    ('deal', 'Получено по сделке'), ('correction', 'Корректировка по сверке'),
]
STATES = ['confirmed'] * 7 + ['pending', 'failed', 'cancelled']


def _ensure_rates(env):
    Rate = env['coop.currency.rate'].sudo()
    if not Rate.search_count([]):
        Rate.coop_fetch_cbr_rates()
    if Rate.search_count([]):
        made = 0
    else:
        made = _seed_rates(env)
    # UGX — устаревший курс: ЦБ его не публикует, ставим давний вручную.
    ugx = env['res.currency'].sudo().with_context(active_test=False).search(
        [('name', '=', 'UGX')], limit=1)
    if ugx and not Rate.search_count([('currency_id', '=', ugx.id)]):
        Rate.create({'currency_id': ugx.id,
                     'date': date.today() - timedelta(days=12),
                     'rub_per_unit': 0.022, 'source': 'manual'})
    return made


def _seed_rates(env):
    Rate = env['coop.currency.rate'].sudo()
    Currency = env['res.currency'].sudo().with_context(active_test=False)
    made = 0
    for code, value in FALLBACK_RATES.items():
        currency = Currency.search([('name', '=', code)], limit=1)
        if currency:
            Rate.create({'currency_id': currency.id, 'date': date.today(),
                         'rub_per_unit': value, 'source': 'manual'})
            made += 1
    return made


def _rate(env, currency):
    rate = env['coop.currency.rate'].coop_rate(currency)
    return rate[0] if rate else 1.0


def _accounts(env, wallet, codes, rnd):
    """Счета по валютам: один основной; у части — второй счёт той же страны."""
    Account = env['coop.wallet.account'].sudo()
    Currency = env['res.currency'].sudo().with_context(active_test=False)
    out = {}
    for code in codes:
        currency = Currency.search([('name', '=', code)], limit=1)
        if not currency:
            continue
        country = currency.coop_country_id or env.ref(
            'base.de' if code == 'EUR' else 'base.us')
        bank = rnd.choice(BANKS)
        main = Account.create({
            'wallet_id': wallet.id, 'country_id': country.id, 'bank': bank,
            'kind': 'bank', 'currency_id': currency.id, 'is_main': True,
            'label': 'Счёт •• %04d, %s' % (rnd.randint(1000, 9999), bank)})
        out[code] = main
        if code in ('CNY', 'KZT', 'EUR') and rnd.random() < 0.6:
            Account.create({
                'wallet_id': wallet.id, 'country_id': country.id,
                'bank': rnd.choice(BANKS), 'kind': 'card',
                'currency_id': currency.id,
                'label': 'Карта •• %04d' % rnd.randint(1000, 9999)})
    return out


def _cbdc(env, wallet, rnd):
    """Счёт «Цифровой рубль»: рядом с банковским рублём, а не вместо него."""
    Account = env['coop.wallet.account'].sudo()
    found = Account.search([('wallet_id', '=', wallet.id), ('kind', '=', 'cbdc')],
                           limit=1)
    if found:
        return found
    rub = env.ref('base.RUB')
    return Account.create({
        'wallet_id': wallet.id, 'country_id': env.ref('base.ru').id,
        'bank': 'Банк России', 'kind': 'cbdc', 'currency_id': rub.id,
        'label': 'Цифровой рубль'})


def _movements(env, wallet, accounts, rnd, per_currency):
    Movement = env['coop.wallet.movement'].sudo().with_context(
        tracking_disable=True)
    for code, account in accounts.items():
        if code == 'CBDC':
            continue
        currency = account.currency_id
        rate = _rate(env, currency)
        count = per_currency.get(code, rnd.randint(5, 14))
        for index in range(count):
            kind, title = rnd.choice(TITLES)
            if kind in ('topup', 'withdraw'):
                target = accounts.get('CBDC') if code == 'RUB' else account
                if code != 'RUB' or not target:
                    kind, title = 'deal', 'Оплата по сделке'
                    target = account
            else:
                target = account
            rub = rnd.randint(2500, 90000)
            amount = round(rub / rate, 2 if rate >= 0.01 else 0) or 1
            sign = 1 if kind in ('topup',) or (kind == 'deal' and index % 2) else -1
            if kind == 'correction':
                sign = rnd.choice([-1, 1])
            # Первое движение — приход, чтобы остаток не уходил в минус.
            if index == 0:
                kind, title, sign = 'topup' if code == 'RUB' and accounts.get('CBDC') else 'deal', \
                    'Получено по сделке', 1
                target = accounts.get('CBDC') if kind == 'topup' else account
                amount = round(rub * 6 / rate, 2 if rate >= 0.01 else 0)
            Movement.create({
                'wallet_id': wallet.id, 'account_id': target.id,
                'currency_id': currency.id,
                'date': '2026-%02d-%02d' % (1 + (index * 3) % 11, 1 + (index * 7) % 27),
                'name': title, 'kind': kind, 'amount': sign * amount,
                'state': 'confirmed' if index == 0 else rnd.choice(STATES)})


def _fix_negative(env, wallet):
    """Остаток в демо не уходит в минус: недостающее — приходом по сделке."""
    Movement = env['coop.wallet.movement'].sudo().with_context(tracking_disable=True)
    for row in wallet.coop_balances():
        if row['balance'] < 0:
            account = wallet.account_ids.filtered(
                lambda a: a.currency_id == row['currency'] and a.kind != 'cbdc')[:1]
            Movement.create({
                'wallet_id': wallet.id, 'account_id': account.id,
                'currency_id': row['currency'].id, 'date': '2026-11-02',
                'name': 'Получено по сделке', 'kind': 'deal',
                'amount': round(-row['balance'] * 1.25, 2), 'state': 'confirmed'})


def load_wallet_currencies(env):
    Wallet = env['coop.wallet'].sudo()
    Account = env['coop.wallet.account'].sudo()
    rnd = random.Random(20261110)
    made = _ensure_rates(env)

    user = env['res.users'].sudo().search([('login', '=', 'dashkevich')], limit=1)
    wallets = []
    if user:
        wallets.append(('rich', Wallet.wallet_for(user.partner_id)))
    others = Wallet.search([('method_ids', '!=', False)], order='id', limit=60)
    shapes = ['rub', 'rub_cny', 'dual', 'rub', 'myr', 'rub', 'ugx', 'rub_cny', 'rub',
              'dual']
    for index, wallet in enumerate(others):
        if user and wallet.partner_id == user.partner_id:
            continue
        wallets.append((shapes[index % len(shapes)], wallet))

    for shape, wallet in wallets:
        # Уже наполнено: есть счёт не в рублях.
        if Account.search_count([('wallet_id', '=', wallet.id),
                                 ('currency_id.name', '!=', 'RUB')]):
            _fix_negative(env, wallet)
            continue
        if shape == 'rub':
            continue
        # Прежние рублёвые счета из способов оплаты остаются как есть.
        existing = {a.currency_id.name: a for a in Account.search(
            [('wallet_id', '=', wallet.id), ('currency_id.name', '=', 'RUB')])}
        if shape == 'rich':
            codes, cbdc = [c for c in RICH if c not in existing], True
        elif shape == 'rub_cny':
            codes, cbdc = ['CNY'], True
        elif shape == 'dual':
            codes, cbdc = ['KZT', 'EUR'], False
            ru, kz = env.ref('base.ru'), env.ref('base.kz')
            wallet.partner_id.sudo().write({
                'coop_citizenship_ids': [(6, 0, [ru.id, kz.id])]})
            if index_even(wallet.id):
                wallet.partner_id.sudo().coop_summary_country_id = kz
        elif shape == 'myr':
            codes, cbdc = ['MYR'], False
        else:
            codes, cbdc = ['UGX'], False
        accounts = dict(existing)
        need = [c for c in codes if c not in existing]
        if cbdc and 'RUB' not in existing and 'RUB' not in need:
            need.append('RUB')
        accounts.update(_accounts(env, wallet, need, rnd))
        if cbdc:
            accounts['CBDC'] = _cbdc(env, wallet, rnd)
        per = {'RUB': 8} if shape != 'rich' else {}
        _movements(env, wallet, accounts, rnd, per)
        _fix_negative(env, wallet)
        made += 1
    return made


def index_even(number):
    return number % 2 == 0
