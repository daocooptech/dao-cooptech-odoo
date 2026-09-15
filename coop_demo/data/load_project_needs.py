# -*- coding: utf-8 -*-
"""Потребности проектов и предложения на них.

Трудовые потребности заводятся вакансиями, а не объявлениями ресурсов:
решение владельца от 14 сентября 2026 — «вакансии из проектов
размещаются в вакансиях а не в ресурсах». Каталог ресурсов про вещи,
работа живёт в своём каталоге, где есть специализация, навыки и отклики.

Потребность — объявление спроса в каталоге ресурсов, привязанное к
проекту. Порядок фрилансовый: на каждую приходят предложения, и
ответственный утверждает одно, остальные отклоняются.

Потребности берутся из того, что проекту действительно нужно, и по тому
же признаку, что и задачи: название проекта говорит, чего он просит.
Теплице нужна рассада и поливальная система, пекарне — мука и печь,
принтеру — бетонная смесь и оператор. Общее для всех — руки, транспорт и
помещение: без них не обходится ни одна затея.

Предложения приходят не от кого попало: откликаются те, у кого в
каталоге есть подходящее, и те, кто уже вложился в этот проект. Часть
потребностей закрыта — по ним видно, как работает утверждение: один
принят, остальные отклонены.
"""
import logging
import random
from datetime import timedelta

from odoo import fields

from . import rubrics

_logger = logging.getLogger(__name__)

# Общее для любой затеи: без рук, перевозки и места не обходится никто.
COMMON = [
    ('Разнорабочие на подготовку площадки', 'labour', 25000),
    ('Перевозка материалов по городу', 'transport', 12000),
    ('Помещение под временное хранение', 'space', 18000),
    ('Бухгалтер на первичку по проекту', 'service', 15000),
]

# Что просит проект, судя по названию. Ключ ищется в названии.
BY_TOPIC = {
    'теплиц': [('Рассада и семена на сезон', 'material', 45000),
               ('Система капельного полива', 'equipment', 80000),
               ('Агроном на запуск', 'labour', 30000)],
    'принтер': [('Бетонная смесь, сорок кубов', 'material', 160000),
                ('Оператор печатной установки', 'labour', 60000),
                ('Опалубка и арматура', 'material', 55000)],
    'пекарн': [('Мука высшего сорта, две тонны', 'material', 70000),
               ('Подовая печь, бывшая в употреблении', 'equipment', 240000),
               ('Пекарь с опытом', 'labour', 55000)],
    'коворкинг': [('Столы и стулья на двадцать мест', 'equipment', 90000),
                  ('Сетевое оборудование и монтаж', 'equipment', 45000)],
    'электростанц': [('Солнечные панели, десять киловатт', 'equipment', 380000),
                     ('Электромонтажник с допуском', 'labour', 70000)],
    'площадк': [('Резиновое покрытие', 'material', 120000),
                ('Игровой комплекс', 'equipment', 200000)],
    'мастерск': [('Станок по дереву', 'equipment', 150000),
                 ('Вытяжка и вентиляция', 'equipment', 60000)],
    'склад': [('Стеллажи паллетные', 'equipment', 110000),
              ('Ворота секционные', 'equipment', 85000)],
    'сыр': [('Молоко от фермеров, тонна в неделю', 'material', 65000),
            ('Сыровар', 'labour', 60000)],
    'пасек': [('Ульи, двадцать штук', 'equipment', 90000),
              ('Вощина и рамки', 'material', 25000)],
    'библиотек': [('Стеллажи и читальные столы', 'equipment', 70000),
                  ('Библиотекарь на полставки', 'labour', 25000)],
    'медиацентр': [('Камера и свет', 'equipment', 130000),
                   ('Монтажёр', 'labour', 45000)],
    'зарядн': [('Зарядная станция на два поста', 'equipment', 280000),
               ('Подключение к сети', 'service', 90000)],

    # ДАО-проекты. Предмет у них другой, и нужно им другое: не доски и
    # не перевозка, а сервер, аудит и техписатель. Пока этих строк не
    # было, «Библиотека паевого учёта» просила разнорабочих на
    # подготовку площадки — по общему списку, который подходит любой
    # затее с лопатой и ни одной с репозиторием.
    'узлы федерации': [('Серверы под узлы, шесть штук', 'equipment', 540000),
                       ('Стойко-место в дата-центре на год', 'space', 180000),
                       ('Инженер по эксплуатации', 'labour', 120000)],
    'библиотека паевого': [('Разработчик на расчётное ядро', 'labour', 180000),
                           ('Ревизия кода сторонним разработчиком', 'service', 90000)],
    'аудит смарт': [('Аудитор смарт-контрактов', 'labour', 400000),
                    ('Повторная проверка после правок', 'service', 150000)],
    'индексатор': [('Разработчик на службу выборок', 'labour', 160000),
                   ('Сервер с быстрыми дисками', 'equipment', 210000)],
    'мобильный клиент': [('Мобильный разработчик', 'labour', 190000),
                         ('Дизайнер интерфейсов', 'labour', 140000),
                         ('Устройства для проверки, пять штук', 'equipment', 120000)],
    'цфа': [('Разработчик интеграции', 'labour', 200000),
            ('Юридическое сопровождение подключения', 'service', 180000)],
    'школа разработчиков': [('Преподаватель курса', 'labour', 120000),
                            ('Запись и монтаж занятий', 'service', 80000)],
    'руководство участника': [('Технический писатель', 'labour', 110000),
                              ('Редактор', 'labour', 70000)],
    'голосования': [('Разработчик на подсчёт голосов', 'labour', 180000),
                    ('Проверка протокола подсчёта', 'service', 140000)],
    'гильдия': [('Разработчик на подряд', 'labour', 170000),
                ('Менеджер заказов', 'labour', 90000)],
    'резервное копирование': [('Дисковый массив', 'equipment', 260000),
                              ('Инженер по резервированию', 'labour', 110000)],
    'реестр лицензий': [('Юрист по лицензиям на ПО', 'labour', 130000),
                        ('Разработчик на разбор зависимостей', 'labour', 90000)],
    'тестовая сеть': [('Серверы под тестовый круг', 'equipment', 240000),
                      ('Инженер по тестированию', 'labour', 120000)],
    'ключи и подписи': [('Разработчик по криптографии', 'labour', 220000),
                        ('Токены и носители ключей', 'equipment', 90000)],
    'датасет цен': [('Аналитик данных', 'labour', 140000),
                    ('Хранилище под выгрузки', 'equipment', 110000)],
    'дежурная служба': [('Дежурный инженер, смена', 'labour', 60000),
                        ('Служба оповещения', 'service', 40000)],
    'перевод интерфейса': [('Переводчик на татарский', 'labour', 70000),
                           ('Переводчик на якутский', 'labour', 70000),
                           ('Редактор переводов', 'labour', 60000)],
    'ретроактивный фонд': [('Разработчик на учёт заявок', 'labour', 150000),
                           ('Ведущий разбора заявок', 'labour', 90000)],
    'защита узлов': [('Специалист по безопасности', 'labour', 210000),
                     ('Разбор попыток подбора', 'service', 80000)],
    'открытая crm': [('Разработчик на Odoo', 'labour', 180000),
                     ('Дизайнер интерфейсов', 'labour', 140000)],
}

# Общее для ДАО-проекта. У затеи с лопатой это руки, перевозка и место;
# у затеи с репозиторием — сервер, документация и ревизия кода.
COMMON_IT = [
    ('Ревизия кода сторонним разработчиком', 'service', 90000),
    ('Виртуальный сервер на год', 'equipment', 96000),
    ('Технический писатель', 'labour', 110000),
]

# Чем откликаются. Текст предложения зависит от того, что просят: на
# «нужен агроном» отвечают «выйду агрономом», а не «привезу щебень».
OFFER_KIND = {
    'labour': ('Возьмусь за работу', 'labour'),
    'equipment': ('Дам своё оборудование', 'resource'),
    'material': ('Поставлю материалы', 'material'),
    'transport': ('Перевезу своим транспортом', 'resource'),
    'space': ('Дам помещение', 'space'),
    'service': ('Сделаю как услугу', 'knowledge'),
}

TARGET_NEEDS = 130


def _рубрика_ресурса(env, name):
    """Номер рубрики по названию, или ложь — как ждёт `create`."""
    имя = rubrics.category_for(name)
    if not имя:
        return False
    рубрика = env['coop.resource.category'].sudo().search(
        [('name', '=', имя)], limit=1)
    return рубрика.id or False


def _специализация(env, name):
    имя = rubrics.specialization_for(name)
    if not имя:
        return False
    спец = env['coop.specialization'].sudo().search(
        [('name', '=', имя)], limit=1)
    return спец.id or False


def load_project_needs(env, target=TARGET_NEEDS):
    Resource = env['coop.resource'].sudo()
    Contribution = env['coop.project.contribution'].sudo()
    Collect = env['coop.project'].sudo()
    Partner = env['res.partner'].sudo()

    # Раньше здесь стоял общий пропуск: «потребностей в базе достаточно —
    # выхожу». Из-за него проекты, пришедшие в каталог позже, не получали
    # ничего: ДАО-проекты завелись без единой потребности и без вакансий,
    # и сбор у них было нечем наполнять. Пропускаем не наполнение
    # целиком, а те проекты, у которых уже что-то есть.
    projects = Collect.search([
        ('state', 'in', ('gathering', 'running', 'done'))], order='id')
    Vacancy = env['coop.vacancy'].sudo() if 'coop.vacancy' in env else None
    have_needs = set(Resource.search([
        ('project_id', 'in', projects.ids)]).mapped('project_id').ids)
    if Vacancy is not None:
        have_needs |= set(Vacancy.search([
            ('coop_project_id', 'in', projects.ids)
        ]).mapped('coop_project_id').ids)
    projects = projects.filtered(lambda p: p.id not in have_needs)
    if not projects:
        _logger.info('Потребности проектов: все проекты наполнены, пропускаю')
        return 0

    # Предел считается от числа ненаполненных проектов, а не берётся
    # числом. Пока он был жёстким (сто тридцать), его съедали первые же
    # проекты по порядку идентификаторов, а последние оставались пустыми
    # навсегда — именно так ДАО-проекты и завелись без единой
    # потребности. Проект без потребностей — проект, в который нельзя
    # войти; в каталоге такому делать нечего.
    target = max(target, 3 * len(projects))
    if not projects:
        _logger.warning('Проектов нет — потребности не завожу')
        return 0

    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)],
        order='id')
    companies = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)],
        order='id')
    if not people:
        _logger.warning('Нет участников — потребности не завожу')
        return 0

    rnd = random.Random(20260914)
    today = fields.Date.today()
    made_needs = made_offers = closed = 0
    # Счётчик закрытых живёт в списке: вакансии заводит отдельная
    # функция, а число закрытых нужно общее.
    closed_box = [0]

    for index, project in enumerate(projects):
        if made_needs >= target:
            break
        common = COMMON_IT if project.kind == 'dao' else COMMON
        rows = list(common[:1])
        # Длинный ключ проверяется раньше короткого. Иначе «Библиотека
        # паевого учёта» совпадает с «библиотек» — той, что со
        # стеллажами и читальными столами, — и ДАО-проект просит
        # библиотекаря на полставки.
        for token, extra in sorted(BY_TOPIC.items(),
                                   key=lambda pair: -len(pair[0])):
            if token in (project.name or '').lower():
                rows = extra + common[:1]
                break
        else:
            rows = [common[index % len(common)],
                    common[(index + 2) % len(common)]]
        # Общая строка может уже стоять в списке темы — тогда проект
        # просит одно и то же дважды.
        seen_titles = set()
        rows = [row for row in rows
                if not (row[0] in seen_titles or seen_titles.add(row[0]))]

        for order, (title, kind, price) in enumerate(rows):
            if made_needs >= target:
                break
            # Ответственный за потребность — не всегда инициатор: на
            # проекте в три десятка нужд он становится узким местом.
            manager = (project.contribution_ids.filtered(
                lambda c: c.state == 'accepted')[:1].partner_id
                if order and project.contribution_ids else False)

            if kind in ('labour', 'service'):
                made_needs += _make_vacancy(
                    env, project, title, price, manager, rnd, today,
                    people, closed_box)
                continue

            with env.cr.savepoint():
                need = Resource.create({
                    'name': title,
                    'listing_type': 'request',
                    'resource_type': {
                        'labour': 'labour', 'equipment': 'equipment',
                        'material': 'material', 'transport': 'equipment',
                        'space': 'equipment', 'service': 'labour',
                    }.get(kind, 'material'),
                    'project_id': project.id,
                    'owner_id': project.partner_id.id,
                    'need_manager_id': manager.id if manager else False,
                    'city': project.city,
                    'price': price,
                    'price_kind': 'to',
                    'description': '<p>Потребность проекта «%s».</p>' % project.name,
                    'state': 'published',
                    # Рубрика выводится из названия тут же: объявление без
                    # раздела не находится отбором и попадает на витрине в
                    # полку «Другое». Раньше её не ставили вовсе, и таких
                    # объявлений накопилось двести семнадцать.
                    'category_id': _рубрика_ресурса(env, title),
                })
                made_needs += 1

            # Предложения: от двух до четырёх, и одно из них может быть
            # от организации — техника и материалы чаще у них.
            offers = []
            for step in range(rnd.randint(2, 4)):
                who = (companies[(index * 3 + step) % len(companies)]
                       if kind in ('equipment', 'material') and step == 0
                       and companies
                       else people[(index * 7 + step * 5) % len(people)])
                if who == project.partner_id:
                    continue
                label, contribution_kind = OFFER_KIND.get(
                    kind, ('Предложу своё', 'service'))
                with env.cr.savepoint():
                    offer = Contribution.create({
                        'project_id': project.id,
                        'need_id': need.id,
                        'partner_id': who.id,
                        'name': '%s: %s' % (label, title.lower()),
                        'kind': contribution_kind,
                        'value': round(price * rnd.uniform(0.75, 1.15), -2),
                        'state': 'offered',
                        'offered_on': today - timedelta(days=rnd.randint(2, 40)),
                    })
                    offers.append(offer)
                    made_offers += 1

            # Часть потребностей уже закрыта: по ним и видно, как
            # работает утверждение — один принят, остальные отклонены.
            if offers and rnd.random() < 0.55:
                chosen = offers[rnd.randrange(len(offers))]
                with env.cr.savepoint():
                    chosen.write({
                        'state': 'accepted',
                        'accepted_on': today - timedelta(days=rnd.randint(0, 5)),
                    })
                    # Закрываем тем же кодом, что и кнопка: иначе
                    # наполнение показывало бы состояние, которого
                    # платформа сама создать не умеет.
                    chosen._close_need()
                    closed += 1

    _logger.info('Потребностей: %s, предложений: %s, закрыто: %s',
                 made_needs, made_offers, closed + closed_box[0])
    return made_needs


def _make_vacancy(env, project, title, price, manager, rnd, today, people,
                  closed_box):
    """Трудовая потребность — вакансия проекта с откликами.

    Вознаграждение долей, а не деньгами: работа в кооперативном проекте
    и есть вклад, от которого считается доля. Деньгами платят там, где
    нанимают, — а нанимает организация, не проект.
    """
    Vacancy = env['coop.vacancy'].sudo()
    Application = env['coop.vacancy.application'].sudo()
    Contribution = env['coop.project.contribution'].sudo()

    with env.cr.savepoint():
        vacancy = Vacancy.create({
            'name': title,
            'coop_project_id': project.id,
            'partner_id': project.partner_id.id,
            'need_manager_id': manager.id if manager else False,
            'city': project.city,
            'contribution_value': price,
            'reward_kind': 'share',
            'state': 'published',
            'description': '<p>Работа нужна проекту «%s».</p>' % project.name,
            'coop_specialization_id': _специализация(env, title),
        })

    applicants = []
    for step in range(rnd.randint(2, 4)):
        who = people[(project.id * 7 + step * 5) % len(people)]
        if who == project.partner_id or who in applicants:
            continue
        applicants.append(who)
        with env.cr.savepoint():
            Application.create({
                'vacancy_id': vacancy.id,
                'partner_id': who.id,
                'state': 'applied',
                'message': 'Возьмусь: %s' % title.lower(),
            })

    # Часть вакансий уже закрыта утверждённым откликом — по ним видно,
    # как работает выбор.
    if applicants and rnd.random() < 0.5:
        chosen = vacancy.application_ids.filtered(
            lambda app: app.state == 'applied')[:1]
        if chosen:
            with env.cr.savepoint():
                contribution = Contribution.create({
                    'project_id': project.id,
                    'partner_id': chosen.partner_id.id,
                    'kind': 'labour',
                    'name': title,
                    'value': price,
                    'state': 'accepted',
                    'accepted_on': today,
                })
                chosen.write({'state': 'invited',
                              'contribution_id': contribution.id})
                others = vacancy.application_ids.filtered(
                    lambda app: app.state == 'applied')
                if others:
                    others.write({'state': 'declined'})
                vacancy.write({'state': 'closed',
                               'need_accepted_id': contribution.id})
                closed_box[0] += 1
    return 1
