# -*- coding: utf-8 -*-
"""Реестр НМА, лицензии и заявки на выпуск ЦФА.

Активы раздаются организациям и кооперативам: рецептура и товарный знак
принадлежат делу, а не человеку. Часть — участникам-мастерам: программа
учёта смен вполне бывает написана одним.

Разброс намеренный. Есть активы с оформленным залогом и без него — на
этой паре и видно главное различие раздела: оценка сама по себе ничего
не обеспечивает. Есть лицензии простые и исключительные, действующие и
истёкшие, с роялти и без. Есть активы, внесённые вкладом в проекты, — по
ним начисляются доли тем же порядком, что и за труд.
"""
import logging
import random

from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

TARGET_ASSETS = 130
TARGET_CFA = 45

KNOW_HOW = [
    ('Рецептура сыра «Дербентский»', 'Режим коммерческой тайны, приказ от 12.03.2025'),
    ('Технология холодного копчения муксуна', 'Режим коммерческой тайны, приказ от 04.09.2024'),
    ('Закваска для ряженки длительного созревания', 'Режим коммерческой тайны, приказ от 17.01.2025'),
    ('Методика обжарки арабики среднего помола', 'Режим коммерческой тайны, приказ от 22.11.2024'),
    ('Состав грунта для рассады томатов', 'Режим коммерческой тайны, приказ от 08.02.2025'),
    ('Технология сушки иван-чая', 'Режим коммерческой тайны, приказ от 30.06.2024'),
    ('Схема раскроя бруса с минимальным отходом', 'Режим коммерческой тайны, приказ от 19.03.2025'),
    ('Рецептура хлеба на закваске без дрожжей', 'Режим коммерческой тайны, приказ от 11.05.2025'),
]

TRADEMARKS = [
    ('Товарный знак «Шукты»', 'Свидетельство № 812344, класс 29'),
    ('Товарный знак «Северный лес»', 'Свидетельство № 799120, класс 19'),
    ('Товарный знак «Двор»', 'Свидетельство № 834501, класс 35'),
    ('Знак обслуживания «Кооп-Ремонт»', 'Свидетельство № 845702, класс 37'),
    ('Товарный знак «Борозда»', 'Свидетельство № 801933, класс 31'),
    ('Товарный знак «Взаимопомощь»', 'Свидетельство № 856110, класс 36'),
]

SOFTWARE = [
    ('Программа учёта смен «Артель»', 'Свидетельство о регистрации ПрЭВМ № 2025618842'),
    ('База данных поставщиков кормов', 'Свидетельство о регистрации БД № 2024621190'),
    ('Программа расчёта паевых взносов', 'Свидетельство о регистрации ПрЭВМ № 2025610455'),
    ('Модуль планирования маршрутов доставки', 'Свидетельство о регистрации ПрЭВМ № 2024617003'),
    ('Программа контроля температуры в камерах', 'Свидетельство о регистрации ПрЭВМ № 2025612288'),
]

PATENTS = [
    ('Способ утепления каркасных стен', 'Патент на изобретение № 2789412'),
    ('Полезная модель: захват для рулонов сена', 'Патент на полезную модель № 221904'),
    ('Сорт пшеницы «Приморская-12»', 'Патент на селекционное достижение № 12094'),
    ('Способ переработки овощных отходов в корм', 'Патент на изобретение № 2801337'),
    ('Порода кур «Забайкальская пёстрая»', 'Патент на селекционное достижение № 11875'),
]

BY_KIND = {
    'know_how': KNOW_HOW,
    'trademark': TRADEMARKS,
    'software': SOFTWARE,
    'patent': PATENTS,
}

TERRITORIES = [
    'Российская Федерация', 'Приморский край', 'Вологодская область',
    'Сибирский федеральный округ', 'Республика Дагестан', 'без ограничений',
]

CFA_NAMES = [
    'Требование по поставке зерна урожая 2027',
    'Денежное требование по договору поставки комбикорма',
    'Требование по оплате монтажных работ',
    'Обязательство по возврату паевого займа',
    'Требование по поставке пиломатериалов',
    'Денежное требование к торговой сети',
]


def load_intangibles(env, target=TARGET_ASSETS, target_cfa=TARGET_CFA):
    Asset = env['coop.intangible'].sudo()
    License = env['coop.intangible.license'].sudo()
    Partner = env['res.partner'].sudo()

    rnd = random.Random(20260907)
    today = fields.Date.context_today(Asset)

    companies = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)], order='id')
    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('coop_verified', '=', True)], order='id', limit=60)
    if not companies:
        _logger.warning('Нет организаций — реестр НМА не наполняю')
        return

    created = skipped = 0
    assets = Asset.browse()
    kinds = list(BY_KIND)
    index = 0
    while created < target:
        kind = kinds[index % len(kinds)]
        variants = BY_KIND[kind]
        base_name, basis = variants[(index // len(kinds)) % len(variants)]
        wave = index // (len(kinds) * len(variants))
        # Второй и третий заходы — те же виды у других правообладателей:
        # рецептура своя у каждого кооператива, и это не повтор строки, а
        # обычное дело.
        owner = (companies[index % len(companies)] if kind != 'software' or not people
                 else (people[index % len(people)] if index % 3 == 0
                       else companies[index % len(companies)]))
        name = base_name if wave == 0 else '%s — %s' % (base_name, owner.name)
        key = 'intangible#%s.%s' % (kind, index)
        index += 1
        if index > target * 4:
            break
        if Asset.search_count([('import_key', '=', key)]):
            skipped += 1
            continue

        cost = float(rnd.choice([
            120000, 260000, 340000, 460000, 620000, 840000, 1200000, 95000]))
        life = rnd.choice([0, 36, 60, 84, 120])
        # Амортизация только у активов с определённым сроком: у ноу-хау и
        # знака срок обычно неопределённый, и они не амортизируются.
        depreciation = round(cost * rnd.uniform(0.05, 0.6), 2) if life else 0.0
        pledge = rnd.choice(
            ['none'] * 6 + ['notary'] * 2 + ['rospatent'])

        asset = Asset.create({
            'name': name,
            'kind': kind,
            'owner_id': owner.id,
            'legal_basis': basis,
            'registration_number': basis.split('№')[-1].strip() if '№' in basis else False,
            'registered_on': today - timedelta(days=rnd.randint(120, 2200)),
            'protection_until': (
                today + timedelta(days=rnd.randint(200, 3600))
                if kind in ('trademark', 'patent') else False),
            'state': rnd.choice(['active'] * 8 + ['draft'] + ['expired']),
            'initial_cost': cost,
            'useful_life_months': life,
            'accumulated_depreciation': depreciation,
            'pledge_state': pledge,
            'pledge_reference': (
                'Уведомление о залоге № %s от %s' % (
                    rnd.randint(100000, 999999),
                    (today - timedelta(days=rnd.randint(30, 900))).strftime('%d.%m.%Y'))
                if pledge != 'none' else False),
            'pledge_holder_id': (
                companies[rnd.randrange(len(companies))].id if pledge != 'none' else False),
            'import_key': key,
        })
        assets |= asset
        created += 1

    _make_licenses(License, assets, companies, people, rnd, today)
    _contribute_to_projects(env, assets, rnd)
    _load_cfa(env, companies, people, rnd, today, target_cfa)

    _logger.info('Реестр НМА: создано %s, пропущено %s', created, skipped)


def _make_licenses(License, assets, companies, people, rnd, today):
    """Лицензии: простые, исключительные, истёкшие и предложенные.

    Исключительная выдаётся не всем и не на всё: две таких на одну
    территорию модель не пропустит, и это правильно — вторая нарушает
    первую. Поэтому исключительные раздаются по одной на актив.
    """
    pool = list(companies) + list(people)
    for asset in assets:
        if asset.license_ids or rnd.random() > 0.45:
            continue
        count = rnd.choice([1, 1, 2, 3])
        used_exclusive = False
        for position in range(count):
            licensee = rnd.choice([p for p in pool if p != asset.owner_id])
            exclusive = (not used_exclusive) and rnd.random() < 0.25
            used_exclusive = used_exclusive or exclusive
            starts = today - timedelta(days=rnd.randint(30, 900))
            length = rnd.choice([365, 730, 1095, 0])
            ends = starts + timedelta(days=length) if length else False
            state = 'active'
            if ends and ends < today:
                state = 'expired'
            elif rnd.random() < 0.15:
                state = 'offered'
            License.create({
                'intangible_id': asset.id,
                'licensee_id': licensee.id if state != 'offered' else False,
                'is_exclusive': exclusive,
                'territory': rnd.choice(TERRITORIES),
                'starts_on': starts,
                'ends_on': ends,
                'volume_limit': rnd.choice([0, 50, 100, 500, 1000]),
                'volume_unit': rnd.choice(['т', 'шт.', 'партий']),
                'price': float(rnd.choice([0, 40000, 90000, 150000, 320000])),
                'royalty_percent': rnd.choice([0, 0, 3, 5, 7.5, 10]),
                'state': state,
                'import_key': 'license#%s.%s' % (asset.id, position),
            })


def _contribute_to_projects(env, assets, rnd):
    """Часть активов внесена вкладом в проекты.

    Вклад правом — то же, что вклад техникой: оценка и доли по той же
    формуле. Без таких записей вкладка «Внесён в проекты» пуста, и связь
    реестра с проектами остаётся словами в описании модуля.
    """
    Contribution = env['coop.project.contribution'].sudo()
    projects = env['coop.project'].sudo().search([], limit=60)
    if not projects:
        return
    for asset in assets:
        if rnd.random() > 0.22 or asset.state != 'active':
            continue
        project = projects[rnd.randrange(len(projects))]
        key = 'intangible.contribution#%s' % asset.id
        if Contribution.search_count([
                ('project_id', '=', project.id),
                ('intangible_id', '=', asset.id)]):
            continue
        contribution = Contribution.create({
            'project_id': project.id,
            'partner_id': asset.owner_id.id,
            'kind': 'knowledge',
            'name': asset.name,
            'value': asset.residual_value or asset.initial_cost,
            'intangible_id': asset.id,
            'state': 'offered',
        })
        # Принимаем часть вкладов: у принятого начисляются доли, у
        # предложенного — нет, и в списке видно оба состояния.
        if rnd.random() < 0.7:
            contribution.write({'state': 'accepted'})
            contribution._grant_shares()


def _load_cfa(env, companies, people, rnd, today, target):
    """Заявки на выпуск ЦФА и купленное у операторов."""
    Issue = env['coop.cfa.issue'].sudo()
    Holding = env['coop.cfa.holding'].sudo()
    operators = env['coop.cfa.operator'].sudo().search([])
    if not operators:
        return

    states = (['draft'] * 8 + ['submitted'] * 6 + ['accepted'] * 4
              + ['issued'] * 12 + ['rejected'] * 3 + ['redeemed'] * 2)
    issued = Issue.browse()
    for position in range(target):
        key = 'cfa.issue#%s' % position
        if Issue.search_count([('import_key', '=', key)]):
            continue
        issuer = companies[position % len(companies)]
        state = rnd.choice(states)
        amount = float(rnd.choice([500000, 1200000, 2500000, 4000000, 8000000]))
        units = rnd.choice([500, 1000, 2000, 5000])
        issue = Issue.create({
            'name': '%s № %s' % (
                CFA_NAMES[position % len(CFA_NAMES)], 2026000 + position),
            'issuer_id': issuer.id,
            'operator_id': operators[position % len(operators)].id,
            'rights_kind': rnd.choice(
                ['money_claim'] * 6 + ['goods_claim'] * 3 + ['share_rights']),
            'amount': amount,
            'unit_count': units,
            'maturity_date': today + timedelta(days=rnd.randint(90, 900)),
            'collateral': rnd.choice([
                False, 'Поручительство кооператива',
                'Залог техники по договору № 14/25',
                'Залог нематериального актива']),
            'state': state,
            'submitted_on': (
                today - timedelta(days=rnd.randint(10, 200))
                if state != 'draft' else False),
            'issued_on': (
                today - timedelta(days=rnd.randint(1, 120))
                if state in ('issued', 'redeemed') else False),
            'external_reference': (
                'ЦФА-%s-%s' % (2026, 10000 + position)
                if state in ('issued', 'redeemed') else False),
            'rejection_reason': (
                'Не подтверждено обеспечение' if state == 'rejected' else False),
            'import_key': key,
        })
        if state in ('issued', 'redeemed'):
            issued |= issue

    # Купленное участниками: часть из наших выпусков, часть со стороны.
    holders = list(people[:40]) + list(companies[:20])
    for position, holder in enumerate(holders):
        if rnd.random() > 0.5:
            continue
        issue = issued[position % len(issued)] if issued else None
        Holding.create({
            'partner_id': holder.id,
            'operator_id': (issue.operator_id if issue
                            else operators[position % len(operators)]).id,
            'issue_id': issue.id if issue and rnd.random() < 0.6 else False,
            'name': issue.name if issue else 'ЦФА на денежное требование',
            'quantity': float(rnd.choice([10, 25, 50, 100, 250])),
            'value': float(rnd.choice([50000, 120000, 300000, 600000])),
            'maturity_date': today + timedelta(days=rnd.randint(60, 800)),
            'source': rnd.choice(['manual'] * 3 + ['operator']),
        })
