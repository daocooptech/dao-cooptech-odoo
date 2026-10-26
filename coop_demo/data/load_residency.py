# -*- coding: utf-8 -*-
"""Резидентство участников — с разбросом (решения 118, 414, п. 1).

Без разброса у всех участников «валютный резидент, налоговый резидент,
Россия», и вкладка «Как рассчитаться» в каждой сделке говорит одно и то
же: рубли можно, валюту нельзя. Правила о валюте, ЦФА, постановке
контракта на учёт и недружественных государствах тогда не видны нигде.

Четыре положения, каждое — настоящий жизненный случай:

- гражданин РФ живёт за границей: валютный резидент (гражданство), но
  налоговый нерезидент (меньше 183 дней в России);
- иностранец без вида на жительство: нерезидент в обоих смыслах;
- иностранец с видом на жительство, живущий в России: резидент в обоих;
- гражданин страны перечня 430-р, живущий там: займы и недвижимость с ним
  закрыты указами № 81 и № 95, остальное — как обычно (решение 500).

Гражданство ставится вместе со страной (решение 500): у живущего за
границей россиянина — Россия, у иностранца — его страна, у иностранца с
видом на жительство — страна, откуда он приехал.

Организации не переселяются. Первая версия (4327bfa) отправила пять
российских компаний в Алматы, Минск, Гуанчжоу и Дубай — «КФХ „Медовый
край“, Дубай» неправдоподобно (владелец 27.09.2026 о таком варианте:
«выглядит неправдоподобно»). Хуже того, каталог организаций ищет запись по
названию и городу, и с чужим городом следующий прогон завёл бы дубль.
Теперь такие организации возвращаются в свой город. Иностранные участники-
организации — по заключению юриста о кооперативном участке за рубежом.

Кому что — по номеру записи, чтобы повторный прогон не переставлял людей
по странам. Главного участника витрины не трогаем: его страница — образец
«обычного» случая.
"""
import io
import json
import logging
import os

from .load_org_profiles import SAMPLES

_logger = logging.getLogger(__name__)
HERE = os.path.dirname(__file__)

# Страна → город. Город меняется вместе со страной: «Владивосток,
# Армения» в карточке читалось бы как ошибка.
ABROAD = [('AM', 'Ереван'), ('GE', 'Тбилиси'), ('KZ', 'Алматы'), ('RS', 'Белград'),
          ('TR', 'Стамбул'), ('AE', 'Дубай'), ('TH', 'Пхукет')]
FOREIGN = [('CN', 'Шанхай'), ('IN', 'Бангалор'), ('BY', 'Минск'), ('UZ', 'Ташкент'),
           ('KZ', 'Астана'), ('VN', 'Хошимин')]
UNFRIENDLY = [('DE', 'Берлин'), ('US', 'Нью-Йорк'), ('FI', 'Хельсинки'), ('LV', 'Рига')]

MAIN_LOGIN = 'dashkevich'


def load_residency(env):
    Partner = env['res.partner'].sudo().with_context(tracking_disable=True)
    if 'coop_fx_resident' not in Partner._fields:
        return
    Country = env['res.country'].sudo()
    countries = {c.code: c for c in Country.search([])}
    russia = countries.get('RU')
    main = env['res.users'].sudo().search([('login', '=', MAIN_LOGIN)], limit=1).partner_id

    counts = {'abroad': 0, 'foreign': 0, 'permit': 0, 'unfriendly': 0,
              'org_home': 0, 'resident': 0}

    def put(partner, fx, tax, code=None, city=None, key='resident', citizen=None):
        country = countries.get(code) if code else russia
        # Гражданство: у валютного резидента — Россия (кроме ВНЖ, там
        # передают явно), у нерезидента — страна, где живёт.
        nationality = countries.get(citizen) if citizen else (russia if fx else country)
        values = {}
        if 'coop_citizenship_id' in partner._fields and nationality                 and partner.coop_citizenship_id != nationality:
            values['coop_citizenship_id'] = nationality.id
        if partner.coop_fx_resident != fx:
            values['coop_fx_resident'] = fx
        if partner.coop_tax_resident != tax:
            values['coop_tax_resident'] = tax
        if country and partner.country_id != country:
            values['country_id'] = country.id
        if city and partner.city != city:
            values['city'] = city
        if values:
            partner.write(values)
        counts[key] += 1

    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], order='id')
    for partner in people:
        if partner == main:
            continue
        seed = partner.id
        if seed % 31 == 0:
            code, city = UNFRIENDLY[seed % len(UNFRIENDLY)]
            put(partner, False, False, code, city, 'unfriendly')
        elif seed % 13 == 0:
            code, city = ABROAD[seed % len(ABROAD)]
            put(partner, True, False, code, city, 'abroad')
        elif seed % 17 == 0:
            code, city = FOREIGN[seed % len(FOREIGN)]
            put(partner, False, False, code, city, 'foreign')
        elif seed % 29 == 0:
            # Вид на жительство: живёт в России, город прежний.
            put(partner, True, True, key='permit',
                citizen=FOREIGN[seed % len(FOREIGN)][0])
        elif (not partner.coop_fx_resident or not partner.coop_tax_resident
              or not partner.country_id):
            # Обычный случай: резидент, живёт в России. Страну ставим и
            # тем, у кого она пуста, — в карточке «Страна» не пустует.
            put(partner, True, True)

    # Организации — российские, в своём городе (см. выше).
    home = _org_home_cities()
    moved = Partner.search([('coop_is_participant', '=', True), ('is_company', '=', True),
                            '|', ('coop_fx_resident', '=', False),
                            ('country_id.code', '!=', 'RU')])
    for partner in moved:
        put(partner, True, True, city=home.get(partner.name), key='org_home')

    # Контрагенты главного участника: по номеру записи ни один из них в
    # разброс не попал, и под его входом вкладка «Как рассчитаться» во всех
    # сделках была одинаковой. Троим — по случаю: живёт за границей,
    # иностранец, житель недружественного государства.
    if main and 'coop.deal' in env:
        deals = env['coop.deal'].sudo().search(
            ['|', ('party_a_id', '=', main.id), ('party_b_id', '=', main.id)], order='id')
        others = []
        for deal in deals:
            other = deal.party_b_id if deal.party_a_id == main else deal.party_a_id
            # Только частные лица: организации не переселяем.
            eligible = other and not other.is_company
            if eligible and other != main and other not in others:
                others.append(other)
        cases = [(True, False, 'AM', 'Ереван', 'abroad'),
                 (False, False, 'CN', 'Шанхай', 'foreign'),
                 (False, False, 'DE', 'Берлин', 'unfriendly')]
        for other, (fx, tax, code, city, key) in zip(others, cases):
            put(Partner.browse(other.id), fx, tax, code, city, key)

    # Российские юрлица без страны — Россия.
    for partner in Partner.search([('coop_is_participant', '=', True), ('is_company', '=', True),
                                   ('country_id', '=', False)]):
        put(partner, True, True)
    _logger.info('Резидентство участников: %s', counts)
    load_currency(env)


def _org_home_cities():
    """Город организации по исходным данным: каталог и образцы профилей."""
    cities = {}
    with io.open(os.path.join(HERE, 'organizations.json'), encoding='utf-8') as fh:
        for org in json.load(fh):
            if org.get('city'):
                cities[org['name']] = org['city']
    for rows in SAMPLES.values():
        for row in rows:
            cities.setdefault(row[0], row[1])
    return cities


# Валюта участника по стране — решение 482: у нерезидентов не рубли. Курсы —
# приблизительные, рублей за единицу (осень 2026): курсов в базе нет, а
# «4 500 юаней» вместо «4 500 рублей» читалось бы как ошибка, поэтому суммы
# пересчитываются, а не просто меняют знак.
CURRENCY_BY_COUNTRY = {
    'CN': 'CNY', 'IN': 'INR', 'BY': 'BYN', 'KZ': 'KZT', 'AE': 'AED', 'TR': 'TRY',
    'BR': 'BRL', 'ZA': 'ZAR', 'US': 'USD', 'DE': 'EUR', 'FI': 'EUR', 'LV': 'EUR',
    'UZ': 'USD', 'VN': 'USD', 'AM': 'USD', 'GE': 'USD', 'RS': 'EUR', 'TH': 'USD',
}
RUB_PER_UNIT = {
    'USD': 95.0, 'EUR': 103.0, 'CNY': 13.0, 'INR': 1.1, 'BYN': 29.0, 'KZT': 0.19,
    'AED': 26.0, 'TRY': 2.8, 'BRL': 17.0, 'ZAR': 5.2,
}
# Объявления и проекты — по стороне, от чьего имени размещены.
LISTINGS = [('coop.resource', 'owner_id'), ('coop.skill.offer', 'partner_id'),
            ('coop.vacancy', 'partner_id'), ('coop.warehouse.offer', 'owner_id'),
            ('coop.auction', 'owner_id'), ('coop.intangible', 'owner_id'),
            ('coop.project', 'partner_id')]


def _nice(amount):
    """Круглая сумма: 346,15 → 350, 1 234 → 1 250, 7,4 → 7."""
    if not amount:
        return amount
    step = 50 if amount >= 1000 else 5 if amount >= 100 else 1
    return max(step, round(amount / step) * step)


def _convert(record, rate):
    """Денежные поля записи и её строк, у которых валюта — от записи."""
    values = {name: _nice(record[name] / rate) for name, field in record._fields.items()
              if field.type == 'monetary' and field.store and not field.compute
              and not field.related and field.get_currency_field(record) == 'currency_id'
              and record[name]}
    for name, field in record._fields.items():
        if field.type != 'one2many' or not field.store:
            continue
        lines = record[name]
        cur = lines._fields.get('currency_id')
        if not lines or not cur or not cur.related or cur.related[-1] != 'currency_id':
            continue
        for line in lines:
            line_values = {n: _nice(line[n] / rate) for n, f in line._fields.items()
                           if f.type == 'monetary' and f.store and not f.compute
                           and not f.related and line[n]}
            if line_values:
                line.write(line_values)
    return values


def load_currency(env):
    Partner = env['res.partner'].sudo()
    if 'coop_currency_id' not in Partner._fields:
        return
    Currency = env['res.currency'].sudo().with_context(active_test=False)
    rub = env.ref('base.RUB')
    codes = set(CURRENCY_BY_COUNTRY.values())
    currencies = {c.name: c for c in Currency.search([('name', 'in', list(codes))])}
    for currency in currencies.values():
        if not currency.active:
            currency.active = True
    chosen = 0
    for partner in Partner.search([('coop_is_participant', '=', True),
                                   ('coop_currency_id', '=', False)]):
        if partner._coop_rub_only():
            continue
        currency = currencies.get(CURRENCY_BY_COUNTRY.get(partner.country_id.code, 'USD'))
        if currency:
            partner.coop_currency_id = currency
            chosen += 1
    converted = 0
    for model, field in LISTINGS:
        if model not in env or 'currency_id' not in env[model]._fields:
            continue
        records = env[model].sudo().with_context(tracking_disable=True).search([
            ('currency_id', '=', rub.id), (field + '.coop_currency_id', '!=', False)])
        for record in records:
            currency = record[field]._coop_currency()
            rate = RUB_PER_UNIT.get(currency.name)
            if currency == rub or not rate:
                continue
            values = _convert(record, rate)
            values['currency_id'] = currency.id
            record.write(values)
            converted += 1
    _logger.info('Валюта участников: выбрана у %s, записей пересчитано %s', chosen, converted)

