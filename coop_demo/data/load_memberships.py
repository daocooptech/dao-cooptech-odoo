# -*- coding: utf-8 -*-
"""Состав организаций: кто в них состоит и что ему позволено.

До сих пор членств в базе было семь — на них не видно ни разницы между
формами, ни разницы между полномочиями. А ровно на этой разнице держится
модель прав: у сотрудника отдела маркетинга нет доступа к бухгалтерии, у
бухгалтера — к управлению страницей.

Должности взяты по формам. В кооперативе есть председатель правления,
пайщики и ревизионная комиссия; в ООО — директор, бухгалтер, менеджеры;
в фонде правления нет, есть директор и попечительский совет. Ставить
пайщиков в ООО значит показывать то, чего не бывает.
"""
import logging
import random

_logger = logging.getLogger(__name__)

# Должность → (основание участия, полномочия, голос).
#
# Полномочия перечислены кодами справочника. Пустой набор значит, что
# человек в организации есть, а делать от её имени ничего не может — так
# и бывает: ассоциированный член вносит пай и не управляет.
JOBS = {
    'chair': ('Председатель правления', 'board',
              ('publish', 'represent', 'deal', 'treasury', 'roster', 'powers', 'site', 'sign'), True),
    'director': ('Директор', 'staff',
                 ('publish', 'represent', 'deal', 'treasury', 'roster', 'powers', 'site', 'sign'), False),
    'deputy': ('Заместитель директора', 'staff',
               ('publish', 'represent', 'deal', 'roster'), False),
    'board': ('Член правления', 'board',
              ('represent', 'deal', 'roster'), True),
    'accountant': ('Бухгалтер', 'staff',
                   ('treasury', 'represent'), False),
    'marketing': ('Специалист отдела маркетинга', 'staff',
                  ('publish', 'represent', 'site'), False),
    'sales': ('Менеджер по продажам', 'staff',
              ('publish', 'represent', 'deal'), False),
    'supply': ('Снабженец', 'staff',
               ('represent', 'deal'), False),
    'auditor': ('Ревизор', 'audit', ('audit',), True),
    'member': ('Пайщик', 'member', ('represent',), True),
    'associate': ('Ассоциированный член', 'associate', (), False),
    'founder': ('Учредитель', 'founder',
                ('represent', 'deal', 'roster', 'powers'), True),
}

# Какие должности бывают в организации какой группы форм. Ключ — код
# группы форм из `coop_base/data/coop_legal_forms.xml`.
BY_GROUP = {
    'cooperative': ['chair', 'board', 'accountant', 'auditor', 'member',
                    'member', 'member', 'associate', 'marketing', 'supply'],
    'commercial': ['director', 'deputy', 'accountant', 'marketing', 'sales',
                   'sales', 'supply', 'founder'],
    'nonprofit': ['director', 'board', 'accountant', 'marketing', 'founder',
                  'member', 'auditor'],
}
FALLBACK = ['director', 'accountant', 'marketing', 'sales']

# Разброс состояний: часть заявлений ещё не рассмотрена, часть членств
# прекращена. Без них экраны «подано заявление» и «прекращено» проверить
# не на чем.
STATES = (['active'] * 16) + ['applied', 'leaving', 'ended']


# Сколько организаций на человека — предел, за которым состав перестаёт
# читаться как правда. Владелец 20 сентября 2026, глядя на страницу
# Беловой: «почему у этого пользователя в друзьях 1 чел, 1 навык,
# 1 проект и куча сообществ и организаций? Можно как то равномерно
# между аккаунтами распределять?» У неё было 28 членств, у рекордсмена —
# 661.
LIMIT_PER_PERSON = 5


def trim_memberships(env):
    """Убрать накопленные и лишние членства.

    Загрузчик заводил состав каждый прогон и ничего не проверял: пара
    «человек — организация» создавалась заново при каждой выкатке, а
    поскольку каталоги между выкатками росли, остаток от деления
    указывал уже на другого человека. За сорок с лишним выкаток из
    ста восьмидесяти членств выросло восемь тысяч, из них 3460
    различных пар — по двадцать организаций на человека.

    Чистка в три прохода: двойники, затем перебор у человека, затем
    проверка, что организация не осталась без состава.
    """
    Membership = env['coop.membership'].sudo()
    all_items = Membership.search([], order='id')

    # Двойники: оставляем самую раннюю запись пары.
    seen = set()
    dupes = Membership
    for membership in all_items:
        key = (membership.partner_id.id, membership.organization_id.id)
        if key in seen:
            dupes |= membership
        else:
            seen.add(key)
    if dupes:
        dupe_count = len(dupes)
        dupes.unlink()
    else:
        dupe_count = 0

    # Перебор у человека. Держим действующие и те, где человек что-то
    # решает: страница, на которой видно только «ассоциированный член»,
    # ничего не показывает о правах.
    def weight(membership):
        sort_order = {'active': 0, 'applied': 1, 'leaving': 2, 'ended': 3}
        main = 0 if membership.role in ('board', 'founder', 'staff') else 1
        return (sort_order.get(membership.state, 4), main, membership.id)

    by_people = {}
    for membership in Membership.search([]):
        partner = membership.partner_id
        if partner.is_company:
            continue
        by_people.setdefault(partner.id, []).append(membership)

    extra = Membership
    for records in by_people.values():
        records.sort(key=weight)
        for membership in records[LIMIT_PER_PERSON:]:
            extra |= membership

    # Организация без состава — хуже, чем человек с лишним членством:
    # у неё пустеет карточка и некому решать заявления.
    left = {}
    for membership in Membership.search([]):
        left.setdefault(membership.organization_id.id, 0)
        left[membership.organization_id.id] += 1
    to_delete = Membership
    for membership in extra:
        org = membership.organization_id.id
        if left.get(org, 0) <= 3:
            continue
        left[org] -= 1
        to_delete |= membership
    removed = len(to_delete)
    if to_delete:
        to_delete.unlink()

    _logger.info('Состав организаций: убрано двойников %s, лишних %s',
                 dupe_count, removed)
    return dupe_count + removed


def load_memberships(env, target=180):
    Membership = env['coop.membership'].sudo()
    Partner = env['res.partner'].sudo()
    Power = env['coop.power'].sudo()

    powers = {p.code: p.id for p in Power.search([])}
    if not powers:
        _logger.warning('Справочник полномочий пуст — состав не наполняю')
        return

    organizations = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)], order='id')
    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)], order='id')
    if not organizations or not people:
        _logger.warning('Нет организаций или людей — состав не наполняю')
        return

    # Воспроизводимость: тот же набор при каждом прогоне, иначе разница
    # между двумя запусками читается как изменение данных.
    rnd = random.Random(20260902)
    created = skipped = 0
    people_pool = list(people)

    for index, organization in enumerate(organizations):
        if created >= target:
            break
        group = organization.coop_legal_form_group_id.code or ''
        jobs = BY_GROUP.get(group) or FALLBACK
        # Сколько человек в этой организации. Крупных мало, мелких много —
        # как в жизни, а не поровну.
        size = rnd.choice([3, 4, 4, 5, 5, 6])
        # Бухгалтер и специалист по маркетингу — в каждой второй
        # организации обязательно: именно на этой паре видно, что права
        # дают полномочия, а не должность и не основание участия. У одного
        # есть доступ к счетам и нет к публикациям, у другого наоборот.
        chosen = ['accountant', 'marketing'] if index % 2 == 0 else []
        rest = [job for job in jobs if job not in chosen]
        chosen += rnd.sample(rest, min(max(size - len(chosen), 1), len(rest)))
        # Председатель или директор — не больше одного: право подписи
        # исключительное, и второй такой записи модель не примет.
        heads = [j for j in chosen if j in ('chair', 'director')]
        for extra in heads[1:]:
            chosen.remove(extra)

        for offset, job in enumerate(chosen):
            person = people_pool[(index * 7 + offset * 13) % len(people_pool)]
            # Пара заводится один раз. Без этой проверки каждая выкатка
            # добавляла состав заново — и у человека набиралось по
            # двадцать организаций, а у одной пары нашлось 123 копии.
            if Membership.search_count([
                    ('partner_id', '=', person.id),
                    ('organization_id', '=', organization.id)]):
                continue
            if Membership.search_count([
                    ('partner_id', '=', person.id)]) >= LIMIT_PER_PERSON:
                continue
            title, role, codes, vote = JOBS[job]
            state = STATES[(index + offset) % len(STATES)]
            values = {
                'partner_id': person.id,
                'organization_id': organization.id,
                'job_title': title,
                'role': role,
                'power_ids': [(6, 0, [powers[c] for c in codes if c in powers])],
                'has_vote': vote and role != 'platform',
                'state': state,
                'joined_on': '20%02d-%02d-%02d' % (
                    20 + (index % 6), 1 + (offset % 12), 1 + ((index + offset) % 27)),
            }
            if state in ('active', 'leaving', 'ended'):
                values['admission_basis'] = 'Протокол № %s от %s' % (
                    1 + (index % 40),
                    values['joined_on'][8:] + '.' + values['joined_on'][5:7]
                    + '.' + values['joined_on'][:4])
            if state == 'ended':
                values['termination_basis'] = 'Заявление о выходе от %s' % (
                    values['admission_basis'].split('от ')[-1])
                values['left_on'] = values['joined_on'].replace(
                    values['joined_on'][:4],
                    str(int(values['joined_on'][:4]) + 2))

            # Точка отката на каждую запись. Без неё первая же
            # непринятая запись обрывает всю транзакцию, и дальше не
            # проходит ничего: PostgreSQL не даёт продолжать работу в
            # прерванной транзакции, сколько её ошибки ни лови.
            try:
                with env.cr.savepoint():
                    Membership.create(values)
                created += 1
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                if skipped <= 3:
                    _logger.warning('Членство не принято: %s', exc)
            if created >= target:
                break

    _logger.info('Состав организаций: создано %s, пропущено %s', created, skipped)
    _ensure_roster_holder(env)


def _ensure_roster_holder(env):
    """В каждой организации должен быть кто-то, кто ведёт состав.

    Заявление о вступлении уходит тому, у кого есть полномочие «Ведение
    состава» (`roster`). Должности раздавались по остатку от деления, и
    в 63 организациях из 189 такого человека не оказалось вовсе:
    заявление там подать можно, а решить его некому.

    Даём полномочие тому, кто и так представляет организацию вовне, —
    правлению, потом любому действующему участнику. Заводить нового
    человека ради этого не нужно.
    """
    Membership = env['coop.membership'].sudo()
    roster = env.ref('coop_base.power_roster', raise_if_not_found=False)
    if not roster:
        return 0
    active_ones = Membership.search([('state', '=', 'active')])
    by_organizations = {}
    for membership in active_ones:
        by_organizations.setdefault(membership.organization_id.id, []).append(membership)

    granted = 0
    for records in by_organizations.values():
        if any('roster' in m.power_ids.mapped('code') for m in records):
            continue
        # Ревизор в кандидаты не годится: модель не даёт выдать
        # ревизионной комиссии исполнительное полномочие — проверяющий не
        # должен быть участником того, что проверяет. Пока в организации
        # было пятеро, ревизор до последней строки перебора не доходил; а
        # после чистки лишних членств нашлись организации, где он остался
        # один, — и обновление модуля упало на этой записи целиком.
        fit = [m for m in records if m.role != 'audit']
        if not fit:
            continue
        # Правление первым: вести состав — его дело по уставу. Если
        # правления нет (общество, а не кооператив) — тот, кто
        # представляет организацию вовне.
        candidate = next(
            (m for m in fit if m.role == 'board'),
            next((m for m in fit
                  if 'represent' in m.power_ids.mapped('code')), fit[0]))
        with env.cr.savepoint():
            candidate.write({'power_ids': [(4, roster.id)]})
            candidate.flush_recordset()
        granted += 1
    if granted:
        _logger.info('Полномочие «Ведение состава» выдано в %s организациях',
                     granted)
    return granted
