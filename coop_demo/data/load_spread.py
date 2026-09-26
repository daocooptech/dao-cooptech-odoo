# -*- coding: utf-8 -*-
"""Поровну между участниками: друзья, сообщества, объявления, проекты.

Зачем. Владелец 20 сентября 2026, глядя на страницу Беловой Инны
Сергеевны: «почему у этого пользователя в друзьях 1 чел, 1 навык,
1 проект и куча сообществ и организаций? Можно как то равномерно между
аккаунтами распределять?»

Пересчёт по боевой базе показал, откуда перекос:

| полка | всего | на человека | ноль у | максимум |
|---|---|---|---|---|
| друзья | 81 связь | 0,5 | 126 из 172 | 6 |
| навыки | 98 | 0,6 | 75 | 2 |
| потребности | 3 | 0,02 | 171 | 3 |
| ресурсы | 740 | 4,3 | 72 | 43 |
| сообщества | 2078 | 12,1 | 69 | 25 |
| организации | 8107 | 47,1 | 0 | **661** |

Причина у всех полок одна и та же, только с разным знаком. Дружбы и
потребности заводились «до целевого числа на всю платформу» — сто
записей на сто семьдесят человек и есть «у одного шесть, у остальных
ноль». А состав организаций заводился каждый прогон заново и ничего не
проверял: за сорок с лишним выкаток из ста восьмидесяти членств выросло
восемь тысяч.

Что делает этот проход. Ровняет по людям то, что уже есть, и дозаводит
то, чего не хватает, — не «сколько-то на платформу», а **на каждого
человека**. Числа взяты из того, как это выглядит на странице: полка из
одной плитки читается как ошибка загрузки, полка из тридцати — как
свалка.

Идемпотентность обязательна: проход выполняется при каждом обновлении
модуля. Всё, что здесь создаётся, сначала проверяется на существование,
а всё, что раздаётся, раздаётся по остатку от номера записи — значит,
второй прогон ничего не меняет.
"""
import logging
import random

_logger = logging.getLogger(__name__)

# Сколько чего полагается человеку. Нижняя граница — чтобы полка не
# выглядела пустой, верхняя — чтобы не выглядела свалкой.
FRIENDS_COUNT = (4, 12)
COMMUNITIES_COUNT = 5
NEEDS_COUNT = 2
OFFERS_COUNT = 2
SKILLS_COUNT = 2
VACANCIES_COUNT = 2
PROJECTS_COUNT = 2
RESOURCES_COUNT = 5

# Личные потребности: чего человек ищет для себя, а не для проекта.
# Взяты бытовые и ремесленные нужды — то, с чем человек приходит на
# платформу сам, а не по работе.
NEEDS = [
    'Ищу бетономешалку в аренду на выходные',
    'Нужен мотоблок на один сезон',
    'Ищу пиломатериал на баню',
    'Нужен электрик на подключение щитка',
    'Ищу мёд с пасеки, небольшую партию',
    'Куплю картофель на зиму, мешками',
    'Ищу швею на пошив штор',
    'Нужен прицеп для перевозки досок',
    'Ищу сварщика на калитку',
    'Куплю саженцы яблони, три-четыре штуки',
    'Ищу место под хранение мотоцикла',
    'Нужна доставка сена до участка',
    'Ищу столяра на кухонный стол',
    'Куплю творог и сыр, каждую неделю',
    'Ищу компрессор на покраску гаража',
    'Нужен мастер на ремонт крыши сарая',
    'Ищу гончарный круг, можно б/у',
    'Куплю ягоду на варенье, ведро-два',
    'Ищу инструмент в прокат на день',
    'Нужен репетитор по информатике для сына',
    'Ищу помощь с уборкой урожая',
    'Куплю дрова колотые, машину',
    'Ищу фотографа на семейный праздник',
    'Нужен ветеринар для кур',
    'Ищу перевозку холодильника по городу',
    'Куплю яйца от домашней птицы',
    'Ищу кого-то на побелку стен',
    'Нужна теплица, поставить на участке',
    'Ищу мастера по заточке инструмента',
    'Куплю пряжу для вязания, шерсть',
]


# Что человек предлагает сам: инструмент, руки, место, урожай. Полка
# «Ресурсы» на странице показывает именно такие объявления —
# предложения без проекта. На платформе их было 114 на всех, и у 171
# человека из 172 полка пустовала.
OFFERS = [
    'Отдам излишки урожая, самовывоз',
    'Сдам бетономешалку на выходные',
    'Продам саженцы со своего питомника',
    'Отдам доски после ремонта',
    'Сдам гараж под хранение',
    'Помогу с электрикой по дому',
    'Продам мёд со своей пасеки',
    'Сдам мотоблок с навесным',
    'Отдам котят в добрые руки',
    'Продам картофель со своего участка',
    'Сдам прицеп для перевозки',
    'Помогу с переездом, есть фургон',
    'Продам домашние яйца, каждую неделю',
    'Отдам старую мебель, самовывоз',
    'Сдам инструмент в прокат',
    'Свяжу на заказ, шерсть своя',
    'Продам варенье и соленья',
    'Помогу с ремонтом крыши',
    'Сдам место в теплице на сезон',
    'Продам дрова колотые с доставкой',
    'Отдам рассаду, вырастил лишнюю',
    'Сложу печь или камин',
    'Продам творог и сыр домашние',
    'Сдам сварочный аппарат',
    'Помогу с вспашкой участка',
    'Продам мебель из массива, на заказ',
    'Отдам банки стеклянные, много',
    'Сдам место под мастерскую',
    'Продам шерсть овечью мытую',
    'Помогу с посадкой сада',
]


def _people(env):
    return env['res.partner'].sudo().search([
        ('is_company', '=', False),
        ('coop_is_participant', '=', True),
    ], order='id')


def ensure_friends(env):
    """Каждому — от четырёх до двенадцати друзей, связи взаимные.

    Дружба заводилась «до целевого числа по платформе»: восемьдесят одна
    связь на сто семьдесят два человека, и сто двадцать шесть страниц
    без единого друга. Полоса «Друзья» на них не показывалась вовсе.

    Кому дружить — решает остаток от номера записи, а не случай: при
    повторном прогоне выходят те же пары, и каталог не пляшет.
    """
    Friendship = env['coop.friendship'].sudo()
    people = _people(env)
    if len(people) < 10:
        return 0
    ids = people.ids
    count_all = len(ids)

    links = set()
    for friendship in Friendship.search([]):
        links.add(tuple(sorted((friendship.requester_id.id,
                                friendship.addressee_id.id))))

    how_many = {}
    for who in ids:
        how_many[who] = sum(1 for pair in links if who in pair)

    created = 0
    for place, who in enumerate(ids):
        # Разное число у разных людей: страница с четырьмя друзьями и
        # страница с двенадцатью должны обе попасться при проверке.
        needed = FRIENDS_COUNT[0] + (place * 5) % (FRIENDS_COUNT[1] - FRIENDS_COUNT[0] + 1)
        step = 1
        while how_many[who] < needed and step < count_all:
            other = ids[(place + step * 7 + 3) % count_all]
            step += 1
            if other == who:
                continue
            pair = tuple(sorted((who, other)))
            if pair in links:
                continue
            if how_many[other] >= FRIENDS_COUNT[1]:
                continue
            with env.cr.savepoint():
                Friendship.create({
                    'requester_id': pair[0],
                    'addressee_id': pair[1],
                    'state': 'accepted',
                })
            links.add(pair)
            how_many[who] += 1
            how_many[other] += 1
            created += 1

    _logger.info('Друзья: заведено связей %s', created)
    return created


def trim_communities(env):
    """Не больше пяти сообществ на человека.

    Двенадцать в среднем и двадцать пять у рекордсмена — это не участие,
    а список всего каталога. Лишнее убираем, но следим, чтобы сообщество
    не осталось без участников: пустое сообщество на витрине хуже, чем
    человек с шестью.
    """
    Member = env['coop.community.member'].sudo()
    by_people, by_communities = {}, {}
    for record in Member.search([], order='id'):
        if record.partner_id.is_company:
            continue
        by_people.setdefault(record.partner_id.id, []).append(record)
        by_communities[record.community_id.id] = \
            by_communities.get(record.community_id.id, 0) + 1

    drop = Member
    for records in by_people.values():
        # Сначала те, где человек что-то значит: в остатке от чистки
        # должны остаться роли, а не только «участник».
        records.sort(key=lambda entry: (0 if entry.role in ('owner', 'moderator') else 1,
                                   0 if entry.state == 'active' else 1, entry.id))
        for record in records[COMMUNITIES_COUNT:]:
            community = record.community_id.id
            if by_communities.get(community, 0) <= 4:
                continue
            by_communities[community] -= 1
            drop |= record

    removed = len(drop)
    if drop:
        drop.unlink()
    _logger.info('Сообщества: убрано лишних участий %s', removed)
    return removed


def _hand_out(env, model, field, limit, picked=None):
    """Раздать записи каталога людям поровну.

    Берём то, что уже принадлежит людям, и перекладываем излишек тем, у
    кого пусто. Записи организаций не трогаем: каталог, где всё
    принадлежит частным лицам, выглядел бы неправдой.
    """
    Model = env[model].sudo()
    people = _people(env)
    if not people:
        return 0
    ids = people.ids
    own_list = set(ids)

    records = Model.search(picked or [], order='id')
    human_ids = [entry for entry in records if entry[field] and entry[field].id in own_list]
    how_many = {i: 0 for i in ids}
    for entry in human_ids:
        how_many[entry[field].id] += 1

    # Кому не хватает — тем и отдаём, начиная с тех, у кого пусто.
    queue = [i for i in ids if how_many[i] == 0] + \
              [i for i in ids if how_many[i] == 1]
    relaid = 0
    for entry in human_ids:
        owner = entry[field].id
        if how_many[owner] <= limit:
            continue
        while queue:
            new = queue.pop(0)
            if new == owner or how_many[new] >= limit:
                continue
            with env.cr.savepoint():
                entry.write({field: new})
            how_many[owner] -= 1
            how_many[new] += 1
            relaid += 1
            break
        else:
            break

    _logger.info('%s: переложено записей %s', model, relaid)
    return relaid


def _top_up_people(env, model, field, keep_for_organizations):
    """Отдать людям записи, которых у них нет, — из числа организаций.

    Перекладывание внутри людей не помогает, когда людям принадлежит
    меньше записей, чем людей: предложений навыка было 98 на 172
    человека, проектов — 88. Полка при этом пустует у половины каталога.

    Часть остаётся за организациями: каталог, где ни один проект не
    начат организацией, выглядел бы так же неправдоподобно, как
    нынешний перекос.
    """
    Model = env[model].sudo()
    people = _people(env)
    if not people:
        return 0
    own_list = set(people.ids)
    records = Model.search([], order='id')
    for_people = {}
    to_organizations = []
    for entry in records:
        owner = entry[field]
        if owner and owner.id in own_list:
            for_people.setdefault(owner.id, 0)
            for_people[owner.id] += 1
        elif owner:
            to_organizations.append(entry)

    empty_ones = [i for i in people.ids if not for_people.get(i)]
    can_take = max(len(to_organizations) - keep_for_organizations, 0)
    given = 0
    for person, record in zip(empty_ones, to_organizations[:can_take]):
        with env.cr.savepoint():
            record.write({field: person})
            record.flush_recordset()
        given += 1
    _logger.info('%s: отдано людям %s из числа организаций', model, given)
    return given


def ensure_personal_offers(env):
    """Личное предложение у каждого — хотя бы одно.

    То же, что и с потребностями, только в другую сторону: полка
    «Ресурсы» на странице человека показывает его предложения, а их на
    платформе было 114 на всех.
    """
    Resource = env['coop.resource'].sudo()
    people = _people(env)
    methods = {m.code: m for m in env['coop.resource.method'].search([])}

    created = 0
    for place, person in enumerate(people):
        exists = Resource.search_count([
            ('owner_id', '=', person.id),
            ('listing_type', '=', 'offer'),
            ('project_id', '=', False),
        ])
        for shift in range(max(OFFERS_COUNT - exists, 0)):
            title = OFFERS[(place * 7 + shift * 11) % len(OFFERS)]
            if Resource.search_count([('owner_id', '=', person.id),
                                      ('name', '=', title)]):
                continue
            # Способ передачи — по первому слову: «сдам» это аренда,
            # «отдам» безвозмездно, «помогу» и «свяжу» — труд.
            bottom = title.lower()
            if bottom.startswith('сдам'):
                code, kind = 'rent', 'equipment'
            elif bottom.startswith('отдам'):
                code, kind = 'free', 'material'
            elif bottom.startswith(('помогу', 'свяжу', 'сложу')):
                code, kind = 'sale', 'labour'
            else:
                code, kind = 'sale', 'material'
            negotiable = (place + shift) % 4 == 0 or code == 'free'
            values = {
                'name': title,
                'owner_id': person.id,
                'listing_type': 'offer',
                'city': person.city or '',
                'resource_type': kind,
                'state': 'published',
                'price_kind': 'none' if negotiable else 'from',
                'price': 0 if negotiable else 300 * (1 + (place + shift) % 15),
            }
            method = methods.get(code) or (list(methods.values())[0] if methods else None)
            if method:
                values['method_ids'] = [(6, 0, [method.id])]
            with env.cr.savepoint():
                record = Resource.create(values)
                record.flush_recordset()
            created += 1

    _logger.info('Ресурсы: заведено личных предложений %s', created)
    return created


def ensure_personal_needs(env):
    """Личная потребность у каждого — хотя бы одна.

    На всю платформу их было три: полка «Потребности» пустовала у ста
    семидесяти одного человека из ста семидесяти двух. Потребности
    проектов сюда не считаются — у них своя полка и свой смысл.
    """
    Resource = env['coop.resource'].sudo()
    people = _people(env)
    methods = {m.code: m for m in env['coop.resource.method'].search([])}
    method = methods.get('sale') or (list(methods.values())[0] if methods else None)
    # Способов передачи у объявления может быть несколько — поле
    # множественное, и одиночное присваивание сюда не подходит.

    created = 0
    for place, person in enumerate(people):
        exists = Resource.search_count([
            ('owner_id', '=', person.id),
            ('listing_type', '=', 'request'),
            ('project_id', '=', False),
        ])
        needed = NEEDS_COUNT - exists
        for shift in range(max(needed, 0)):
            title = NEEDS[(place * 3 + shift * 7) % len(NEEDS)]
            if Resource.search_count([('owner_id', '=', person.id),
                                      ('name', '=', title)]):
                continue
            # Цена у спроса — сколько человек готов заплатить. Без неё
            # запись не проходит проверку: «для способа „Продажа“ нужна
            # цена или оценка». Каждая пятая — договорная: пустая цена
            # тоже должна попадаться при проверке экрана.
            negotiable = (place + shift) % 5 == 0
            values = {
                'name': title,
                'owner_id': person.id,
                'listing_type': 'request',
                'city': person.city or '',
                'resource_type': 'material',
                'state': 'published',
                'price_kind': 'none' if negotiable else 'to',
                'price': 0 if negotiable else 500 * (1 + (place + shift) % 12),
            }
            if method:
                values['method_ids'] = [(6, 0, [method.id])]
            with env.cr.savepoint():
                record = Resource.create(values)
                # Проверки полей срабатывают при сбросе на диск, а он по
                # умолчанию откладывается до конца транзакции — то есть
                # за пределы точки отката. Тогда одна негодная запись
                # роняет всё обновление модуля, а не себя одну; так и
                # вышло 20 сентября 2026 с ценой у спроса.
                record.flush_recordset()
            created += 1

    _logger.info('Потребности: заведено личных объявлений %s', created)
    return created


def spread_all(env):
    """Выровнять полки на страницах людей."""
    total = {}
    total['specializations'] = ensure_extra_specializations(env)
    total['friends'] = ensure_friends(env)
    total['communities'] = trim_communities(env)
    total['needs'] = ensure_personal_needs(env)
    total['resources'] = _hand_out(
        env, 'coop.resource', 'owner_id', RESOURCES_COUNT,
        [('listing_type', '=', 'offer'), ('project_id', '=', False)])
    total['offers'] = ensure_personal_offers(env)
    # Навыки и проекты добираются у организаций: перекладывать внутри
    # людей нечего — записей у них меньше, чем самих людей.
    total['skills_of_people'] = _top_up_people(
        env, 'coop.skill.offer', 'partner_id', keep_for_organizations=40)
    total['projects_of_people'] = _top_up_people(
        env, 'coop.project', 'partner_id', keep_for_organizations=70)
    total['skills'] = _hand_out(env, 'coop.skill.offer', 'partner_id', SKILLS_COUNT)
    total['vacancies'] = _hand_out(env, 'coop.vacancy', 'partner_id', VACANCIES_COUNT,
                                [('project_id', '=', False)])
    total['projects'] = _hand_out(env, 'coop.project', 'partner_id', PROJECTS_COUNT)
    total['titles'] = dedupe_resource_titles(env)
    _logger.info('Выравнивание полок: %s', total)
    return total


def ensure_extra_specializations(env):
    """Раздать людям вторые и третьи специализации.

    Решение 381 от 22 сентября 2026: человек виден на всех подходящих
    полках. Пока у каждого по одной специализации, множественность есть
    в модели и не видна на экране — а невидимая возможность всё равно
    что отсутствующая.

    Раздаётся **не всем и не поровну**. У большинства одна специальность,
    у части две, у немногих три: так и бывает. Каталог, где у каждого
    ровно по две, выглядит сгенерированным, потому что он такой и есть.

    Вторая специальность берётся из своей же сферы или из соседней, а не
    откуда попало: «кузнец и веб-разработчик» — не разнообразие данных, а
    насмешка над ними. Кооперация складывается из смежных умений.
    """
    Partner = env['res.partner'].sudo()
    Specialization = env['coop.specialization'].sudo()

    # Сперва — главная специализация тем, у кого её нет вовсе. Померено
    # 23 сентября 2026: из 191 участника специализация стояла у 103, и
    # остальные 88 валились одной кучей в полку «Другое». Полка, в
    # которой лежит половина каталога, отвечает на вопрос «что здесь
    # бывает» хуже, чем отсутствие полок.
    #
    # Раздаётся по кругу, а не случайно: так полки получаются
    # сопоставимого размера, и ни одна не вырождается в одну карточку.
    nameless = Partner.search([
        ('coop_is_participant', '=', True),
        ('is_company', '=', False),
        ('coop_specialization_id', '=', False),
    ])
    if nameless:
        all_specializations = Specialization.search([], order='id')
        if all_specializations:
            for index, person in enumerate(nameless):
                person.coop_specialization_id =                     all_specializations[index % len(all_specializations)]
            _logger.info('Специализации: главная проставлена %s людям',
                         len(nameless))

    people = Partner.search([
        ('coop_is_participant', '=', True),
        ('is_company', '=', False),
        ('coop_specialization_id', '!=', False),
    ])
    if not people:
        return 0

    # Специализации, разложенные по сферам: вторая берётся из той же
    # сферы или из соседней.
    by_category = {}
    for specialization in Specialization.search([]):
        by_category.setdefault(specialization.category_id.id, []).append(
            specialization)
    if not by_category:
        return 0
    categories = sorted(by_category)

    rnd = random.Random(20260923)
    given = 0
    for person in people:
        if person.coop_specialization_ids:
            continue
        main = person.coop_specialization_id
        chance = rnd.random()
        if chance < 0.55:
            # Больше половины людей умеют что-то одно — и это честно.
            extra_count = 0
        elif chance < 0.88:
            extra_count = 1
        else:
            extra_count = 2

        picked = main
        own = list(by_category.get(main.category_id.id, []))
        for _step in range(extra_count):
            if rnd.random() < 0.6 and len(own) > 1:
                pool = own
            else:
                # Соседняя сфера: не любая, а следующая по справочнику —
                # он упорядочен по смыслу, и соседи в нём ближе друг к
                # другу, чем случайная пара.
                index = categories.index(main.category_id.id) \
                    if main.category_id.id in categories else 0
                neighbour = categories[(index + 1) % len(categories)]
                pool = by_category.get(neighbour, own)
            fit = [s for s in pool if s not in picked]
            if not fit:
                continue
            picked |= rnd.choice(fit)

        if len(picked) > 1:
            person.coop_specialization_ids = [(6, 0, picked.ids)]
            given += 1

    _logger.info('Специализации: вторая и третья розданы %s людям', given)
    return given


# Уточнения к одинаковым объявлениям в одном городе — по первому слову.
_QUALIFIERS = {
    'ищу': ['срочно', 'на этой неделе', 'можно б/у', 'недорого', 'рядом с домом',
            'на выходные', 'с доставкой', 'для дачи'],
    'куплю': ['недорого', 'можно б/у', 'регулярно', 'с доставкой', 'оптом',
              'на этой неделе', 'для хозяйства', 'срочно'],
    'нужен': ['срочно', 'на выходные', 'недорого', 'на сезон', 'с опытом',
              'на этой неделе', 'рядом с домом', 'по договору'],
    'нужна': ['срочно', 'на выходные', 'недорого', 'на сезон', 'с опытом',
              'на этой неделе', 'рядом с домом', 'по договору'],
    'сдам': ['недорого', 'надолго', 'посуточно', 'с доставкой', 'с залогом',
             'на выходные', 'помесячно', 'по договору'],
    'отдам': ['даром', 'срочно', 'самовывоз сегодня', 'в хорошие руки', 'пока есть',
              'на этой неделе', 'много', 'помогу погрузить'],
    'продам': ['недорого', 'с доставкой', 'оптом дешевле', 'свежее', 'с документами',
               'в наличии', 'на заказ', 'от производителя'],
    'помогу': ['недорого', 'в выходные', 'по вечерам', 'с инструментом', 'с опытом',
               'за продукты', 'по договору', 'быстро'],
}
_DEFAULT_QUALIFIERS = ['недорого', 'в наличии', 'по договору', 'с доставкой', 'срочно',
                       'на выгодных условиях', 'рядом', 'на заказ']


def dedupe_resource_titles(env):
    """Одинаковые заголовки в «Ресурсах» — различимыми (решение 416).

    Генераторы личных предложений и потребностей брали заголовок из
    короткого списка, и в каталоге стояло по двадцать «Ищу бетономешалку в
    аренду на выходные», а у проектов — по девяносто «Расходные материалы
    для монтажа». Копии одной строки каталогом не считаются.

    Первое объявление с заголовком остаётся как есть. Потребности проекта
    получают название проекта; личные объявления — город, как уже принято
    в данных («Генератор на 5 кВт — Екатеринбург»); если и город
    совпал — уточнение по первому слову («срочно», «можно б/у»).
    Повторный запуск ничего не меняет: копий не остаётся.
    """
    Resource = env['coop.resource'].sudo().with_context(active_test=False,
                                                        tracking_disable=True)
    records = Resource.search([], order='id')
    taken = set()
    by_name = {}
    for record in records:
        by_name.setdefault(record.name, []).append(record)
    renamed = 0
    for name, group in by_name.items():
        taken.add(name)
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        for index, record in enumerate(group[1:], start=1):
            base = name
            if record.project_id:
                candidates = ['%s — %s' % (base, record.project_id.name)]
            else:
                candidates = []
                if record.city and ('— %s' % record.city) not in base:
                    candidates.append('%s — %s' % (base, record.city))
                word = (base.split(' ', 1)[0] or '').lower()
                # Город уже в заголовке («Генератор — Самара») — второй раз
                # его не дописываем.
                city = record.city if record.city and record.city not in base else ''
                for qualifier in _QUALIFIERS.get(word, _DEFAULT_QUALIFIERS):
                    candidates.append('%s, %s%s' % (
                        base, qualifier, (' — %s' % city) if city else ''))
            new = next((c for c in candidates if c not in taken), None)
            if not new:
                new = '%s (%s)' % (candidates[0] if candidates else base, index + 1)
                if new in taken:
                    continue
            taken.add(new)
            record.name = new
            renamed += 1
    if renamed:
        _logger.info('Ресурсы: одинаковые заголовки сделаны различимыми у %s', renamed)
    return renamed
