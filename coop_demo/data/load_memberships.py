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
