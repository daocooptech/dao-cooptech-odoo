# -*- coding: utf-8 -*-
"""Реестры, которые на 20 оказались пустыми (обход 07.10.2026).

«Заявки с сайта», «Полномочия», «Сотрудники», «История звонков» — у всех
были разделы в меню и ни одной записи: на 19 их наполнять было некому,
а на 20 обход меню показал пустые списки с образцами движка на латыни.
Норма каталога — 100–200 правдоподобных записей во всех состояниях.

Каждая функция смотрит, наполнен ли уже её реестр, и при повторном
запуске ничего не задваивает.
"""
import logging
import random
from datetime import datetime, time, timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

CONTACT_TOTAL = 120
GRANT_TOTAL = 100
EMPLOYEE_TOTAL = 150
CALL_TOTAL = 120

CONTACT_LINES = {
    'node': [
        'Хотим поднять свой узел для кооператива в {city}. Какие требования к серверу?',
        'У нас уже есть сервер в {city}, можно ли подключить его к сети как узел?',
        'Подскажите, сколько стоит сопровождение собственного узла и кто обновляет?',
        'Готовы держать узел для района, нужна инструкция по развёртыванию.',
    ],
    'partner': [
        'Мы оператор ЭДО в {city}, предлагаем партнёрство для организаций сети.',
        'Банк региона готов вести счета кооперативов платформы — с кем обсудить?',
        'Логистическая компания из {city}: хотим возить грузы участников по договору.',
        'Можем быть оператором приёма платежей, интересны условия подключения.',
    ],
    'org': [
        'Хотим подключить наш кооператив из {city}, 40 пайщиков. С чего начать?',
        'ООО из {city}: можно ли работать на платформе вместе с кооперативами?',
        'Фонд поддержки ремёсел, {city} — нужна страница организации и сбор средств.',
        'Сельхозкооператив, {city}: интересуют совместные закупки и склад.',
        'АНО хочет вести на платформе волонтёров и пожертвования. Это возможно?',
    ],
    'other': [
        'Не приходит письмо подтверждения после регистрации.',
        'Можно ли выгрузить историю сделок в таблицу для бухгалтера?',
        'Предлагаю добавить раздел для обмена семенами.',
        'Где посмотреть правила расчёта доверия участника?',
        'Как перенести паевой взнос из одного кооператива в другой?',
    ],
}
ORG_SUFFIXES = ['ПК «{w}»', 'ООО «{w}»', 'СПоК «{w}»', 'АНО «{w}»', 'Фонд «{w}»', 'АО «{w}»']
ORG_WORDS = ['Северный край', 'Народный двор', 'Урожай', 'Мастеровые', 'Рассвет', 'Ладога',
             'Белые росы', 'Добрый хлеб', 'Сибирская артель', 'Волжские промыслы', 'Кедр',
             'Солнечная долина', 'Медоносы', 'Своя земля', 'Тайга-лес']

GRANT_BASES = [
    'Ведение модерации каталогов в часы пик — нагрузка выросла вдвое.',
    'Разбор споров по сделкам округа: нужен доступ к переписке сторон.',
    'Сопровождение узла и выкатка обновлений.',
    'Временная замена дежурного администратора на время отпуска.',
    'Проверка документов организаций при подключении.',
    'Работа с обращениями участников из формы на сайте.',
    'Настройка разделов для нового кооперативного участка.',
]

DEPARTMENTS = ['Правление', 'Бухгалтерия', 'Разработка', 'Поддержка участников',
               'Модерация', 'Склад и логистика', 'Продажи и закупки', 'Юридическая служба']
JOBS = {
    'Правление': ['Председатель', 'Член правления', 'Секретарь правления'],
    'Бухгалтерия': ['Главный бухгалтер', 'Бухгалтер', 'Кассир'],
    'Разработка': ['Ведущий разработчик', 'Разработчик', 'Тестировщик', 'Системный администратор'],
    'Поддержка участников': ['Руководитель поддержки', 'Специалист поддержки'],
    'Модерация': ['Старший модератор', 'Модератор'],
    'Склад и логистика': ['Заведующий складом', 'Кладовщик', 'Логист', 'Водитель-экспедитор'],
    'Продажи и закупки': ['Менеджер по закупкам', 'Менеджер по продажам'],
    'Юридическая служба': ['Юрист', 'Специалист по договорам'],
}


def _when(rnd, now, max_days):
    day = now - timedelta(days=rnd.randint(0, max_days))
    return datetime.combine(day.date(), time(rnd.randint(7, 22), rnd.randint(0, 59)))


def _people(env):
    return env['res.partner'].sudo().search(
        [('coop_is_participant', '=', True), ('is_company', '=', False)], order='id')


def load_contact_requests(env, rnd=None):
    if 'coop.contact.request' not in env:   # модуль раздела не установлен на этом узле
        return 0
    rnd = rnd or random.Random(20261007)
    Request = env['coop.contact.request'].sudo()
    if Request.search_count([]) >= 40:
        return 0
    people = _people(env)
    now = fields.Datetime.now()
    made = 0
    for index in range(CONTACT_TOTAL):
        person = people[rnd.randrange(len(people))] if people else False
        topic = rnd.choice(['org'] * 4 + ['other'] * 3 + ['node'] * 2 + ['partner'] * 2)
        city = (person and person.city) or rnd.choice(['Москва', 'Казань', 'Пермь', 'Сочи'])
        name = person.name if person and rnd.random() < 0.7 else rnd.choice(
            ['Ирина', 'Олег Петрович', 'Мария Соколова', 'Андрей', 'Светлана В.', 'Тимур'])
        contact = (person.email if person and person.email and rnd.random() < 0.6
                   else '+7 9%02d %03d-%02d-%02d' % (rnd.randint(0, 99), rnd.randint(0, 999),
                                                     rnd.randint(0, 99), rnd.randint(0, 99)))
        org = (rnd.choice(ORG_SUFFIXES).format(w=rnd.choice(ORG_WORDS))
               if topic in ('org', 'partner', 'node') else False)
        created = _when(rnd, now, 200)
        age = (now - created).days
        state = ('new' if age < 5 else
                 rnd.choice(['answered'] * 5 + ['closed'] * 3 + ['new']))
        record = Request.create({
            'name': name,
            'email': contact,
            'organization': org,
            'topic': topic,
            'message': rnd.choice(CONTACT_LINES[topic]).format(city=city),
            'state': state,
        })
        env.cr.execute('UPDATE coop_contact_request SET create_date = %s WHERE id = %s',
                       (created, record.id))
        made += 1
    _logger.info('Заявки с сайта: %s', made)
    return made


def load_admin_grants(env, rnd=None, login='dashkevich'):
    """Решения о полномочиях: голосования, отказы, отзывы.

    Права администратора на платформе — у одного человека, `dashkevich`, и
    включаются его переключателем в шапке (решение владельца; так было и в
    19). Поэтому «выданы» — только его решение; у остальных — голосования,
    отказы и отзывы. Технический `admin` решения не получает.
    """
    if 'coop.admin.grant' not in env:   # модуль раздела не установлен на этом узле
        return 0
    rnd = rnd or random.Random(20261008)
    Grant = env['coop.admin.grant'].sudo()
    if Grant.search_count([]) >= 30:
        return 0
    people = _people(env)
    owner = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    today = fields.Date.context_today(Grant)
    made = 0
    granted_left = list(owner.partner_id)
    for index in range(GRANT_TOTAL):
        if granted_left and index % 25 == 0:
            partner = granted_left.pop(0)
            state = 'granted'
        else:
            partner = people[rnd.randrange(len(people))]
            if owner and partner == owner.partner_id:
                continue
            state = rnd.choice(['rejected'] * 4 + ['revoked'] * 3 + ['proposed'] * 2)
        team = rnd.randint(5, 11)
        voters = people.browse(rnd.sample(people.ids, min(team, len(people))))
        if state in ('granted', 'revoked'):
            votes_for = rnd.randint(team // 2 + 1, team)
        elif state == 'rejected':
            votes_for = rnd.randint(0, team // 2)
        else:
            votes_for = rnd.randint(0, team // 2)
        decided = today - timedelta(days=rnd.randint(3, 400))
        vals = {
            'partner_id': partner.id,
            'basis': rnd.choice(GRANT_BASES),
            'voter_ids': [(6, 0, voters.ids)],
            'votes_for': votes_for,
            'votes_against': team - votes_for if state != 'proposed' else rnd.randint(0, 2),
            'state': state,
            'decided_on': decided if state != 'proposed' else False,
            'revoked_on': (decided + timedelta(days=rnd.randint(10, 120))
                           if state == 'revoked' else False),
        }
        if vals['revoked_on'] and vals['revoked_on'] > today:
            vals['revoked_on'] = today
        Grant.create(vals)
        made += 1
    if owner:
        owner._coop_sync_admin_grant()   # признак «выданы» — для переключателя
    _logger.info('Полномочия: %s', made)
    return made


def load_employees(env, rnd=None):
    if 'hr.employee' not in env:   # модуль раздела не установлен на этом узле
        return 0
    rnd = rnd or random.Random(20261009)
    Employee = env['hr.employee'].sudo()
    if Employee.search_count([]) >= 40:
        return 0
    people = _people(env)[:EMPLOYEE_TOTAL]
    company = env.company
    Department = env['hr.department'].sudo()
    departments = {}
    for name in DEPARTMENTS:
        departments[name] = Department.search(
            [('name', '=', name), ('company_id', '=', company.id)], limit=1) or \
            Department.create({'name': name, 'company_id': company.id})
    heads = {}
    made = 0
    for index, person in enumerate(people):
        dept_name = DEPARTMENTS[index % len(DEPARTMENTS)] if index < len(DEPARTMENTS) \
            else rnd.choice(DEPARTMENTS)
        jobs = JOBS[dept_name]
        title = jobs[0] if dept_name not in heads else rnd.choice(jobs[1:] or jobs)
        employee = Employee.create({
            'name': person.name,
            'work_contact_id': person.id,
            'company_id': company.id,
            'department_id': departments[dept_name].id,
            'job_title': title,
            'parent_id': heads.get(dept_name, Employee).id or False,
            'mobile_phone': person.phone or False,
            'active': rnd.random() > 0.06,   # уволенные тоже бывают
        })
        if dept_name not in heads:
            heads[dept_name] = employee
            departments[dept_name].manager_id = employee
        made += 1
    _logger.info('Сотрудники: %s', made)
    return made


def load_call_history(env, rnd=None):
    if 'discuss.call.history' not in env:   # модуль раздела не установлен на этом узле
        return 0
    rnd = rnd or random.Random(20261010)
    History = env['discuss.call.history'].sudo()
    if History.search_count([]) >= 40:
        return 0
    channels = env['discuss.channel'].sudo().search(
        [('channel_type', 'in', ['chat', 'group']), ('coop_kind', '!=', 'service')], order='id')
    if not channels:
        return 0
    now = fields.Datetime.now()
    made = 0
    for index in range(CALL_TOTAL):
        channel = channels[rnd.randrange(len(channels))]
        start = _when(rnd, now, 150)
        # Пропущенные — короче минуты, обычные — до часа, совещания — дольше.
        minutes = rnd.choice([0.3, 0.5] + [rnd.randint(2, 25) for _ in range(6)]
                             + [rnd.randint(40, 95)])
        History.create({
            'channel_id': channel.id,
            'start_dt': start,
            'end_dt': start + timedelta(minutes=minutes),
        })
        made += 1
    _logger.info('История звонков: %s', made)
    return made


def load_registries(env):
    return (load_contact_requests(env) + load_admin_grants(env)
            + load_employees(env) + load_call_history(env))
