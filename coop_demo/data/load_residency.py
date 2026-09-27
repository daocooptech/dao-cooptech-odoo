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
- житель недружественного государства — режим спецсчетов и разрешений.

Кому что — по номеру записи, чтобы повторный прогон не переставлял людей
по странам. Главного участника витрины не трогаем: его страница — образец
«обычного» случая.
"""
import logging

_logger = logging.getLogger(__name__)

# Страна → город. Город меняется вместе со страной: «Владивосток,
# Армения» в карточке читалось бы как ошибка.
ABROAD = [('AM', 'Ереван'), ('GE', 'Тбилиси'), ('KZ', 'Алматы'), ('RS', 'Белград'),
          ('TR', 'Стамбул'), ('AE', 'Дубай'), ('TH', 'Пхукет')]
FOREIGN = [('CN', 'Шанхай'), ('IN', 'Бангалор'), ('BY', 'Минск'), ('UZ', 'Ташкент'),
           ('KZ', 'Астана'), ('VN', 'Хошимин')]
UNFRIENDLY = [('DE', 'Берлин'), ('US', 'Нью-Йорк'), ('FI', 'Хельсинки'), ('LV', 'Рига')]
FOREIGN_ORGS = [('CN', 'Гуанчжоу'), ('BY', 'Минск'), ('KZ', 'Алматы'), ('AE', 'Дубай')]

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
              'foreign_org': 0, 'resident': 0}

    def put(partner, fx, tax, code=None, city=None, key='resident'):
        country = countries.get(code) if code else russia
        values = {}
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
            put(partner, True, True, key='permit')
        elif (not partner.coop_fx_resident or not partner.coop_tax_resident
              or not partner.country_id):
            # Обычный случай: резидент, живёт в России. Страну ставим и
            # тем, у кого она пуста, — в карточке «Страна» не пустует.
            put(partner, True, True)

    # Иностранные организации — только коммерческие: кооператив и НКО в
    # демо — российские юрлица.
    orgs = Partner.search([('coop_is_participant', '=', True), ('is_company', '=', True),
                           ('coop_legal_form_group_id.code', '=', 'commercial')], order='id')
    for partner in orgs:
        if partner.id % 11 == 0:
            code, city = FOREIGN_ORGS[partner.id % len(FOREIGN_ORGS)]
            put(partner, False, False, code, city, 'foreign_org')
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
            eligible = other and (not other.is_company
                                  or other.coop_legal_form_group_id.code == 'commercial')
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
