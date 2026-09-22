# -*- coding: utf-8 -*-
"""Образование, достижения и контакты участников.

Без этого полосы «Образование» и «Достижения» на каждой странице пусты,
и не видно ни того, как они выглядят с тремя записями, ни того, как
ведут себя с одной, ни как страница читается, когда у человека нет
ничего.

Заполнены намеренно не все: примерно у трети участников биографии нет
вовсе — так и в жизни, и пустое состояние страницы должно попадаться
при проверке само, а не только когда его специально ищут.
"""
import logging
import random

_logger = logging.getLogger(__name__)

SCHOOLS = [
    ('ПТУ №30', 'Электромонтажник', 'college'),
    ('Красноярский аграрный техникум', 'Агроном', 'college'),
    ('Сибирский федеральный университет', 'Строительство', 'higher'),
    ('Уральский государственный горный университет', 'Горное дело', 'higher'),
    ('Кубанский государственный аграрный университет', 'Агрономия', 'higher'),
    ('Казанский национальный исследовательский технический университет',
     'Машиностроение', 'higher'),
    ('Новосибирский государственный технический университет',
     'Электроэнергетика', 'higher'),
    ('Политехнический колледж №8', 'Сварочное производство', 'college'),
    ('Курсы «Яндекс Практикум»', 'Веб-разработка', 'courses'),
    ('Учебный центр «Профи»', 'Оператор станков с ЧПУ', 'courses'),
    ('Тюменский индустриальный университет', 'Нефтегазовое дело', 'higher'),
    ('Вологодский аграрно-экономический колледж', 'Зоотехния', 'college'),
]

ACHIEVEMENTS = [
    ('Победитель регионального конкурса «Молодой предприниматель»', True),
    ('Собрал две тонны пластика на раздельный сбор', False),
    ('Первое место в чемпионате WorldSkills, сварка', True),
    ('Запустил кооперативную теплицу на 40 пайщиков', False),
    ('Победитель форума «Территория смыслов»', True),
    ('Наставник года в местном отделении кооперации', False),
    ('Восстановил заброшенную пасеку на 30 ульев', False),
    ('Патент на способ утепления каркасных стен', True),
    ('Организовал совместную закупку кормов на 12 хозяйств', False),
    ('Благодарность администрации района за помощь при паводке', False),
]

LANGUAGES = [
    'русский', 'русский, английский', 'русский, татарский',
    'русский, украинский', 'русский, английский, немецкий',
    'русский, якутский', 'русский, башкирский', 'русский, армянский',
]

# Свободные строки контактов: название человек выбирает сам,
# поэтому и в демонстрации они разные, а не одного образца.
CONTACT_WAYS = [
    ('Telegram', '@%s'),
    ('WhatsApp', '+7 9%s'),
    ('Viber', '+7 9%s'),
    ('GitHub', 'github.com/%s'),
    ('Хабр', 'habr.com/ru/users/%s'),
    ('Дзен', 'dzen.ru/%s'),
    ('VK', 'vk.com/%s'),
    ('Max', '@%s'),
]


def contact_lines(env, partner, rnd, count=None):
    """Завести человеку несколько свободных строк связи."""
    Line = env['coop.contact.line']
    if Line.search_count([('partner_id', '=', partner.id)]):
        return 0
    made = 0
    handle = 'coop%s' % partner.id
    number = '%02d %s-%02d-%02d' % (rnd.randint(10, 99),
                                    rnd.randint(100, 999),
                                    rnd.randint(10, 99), rnd.randint(10, 99))
    for index, (name, shape) in enumerate(
            rnd.sample(CONTACT_WAYS, k=count or rnd.randint(1, 3))):
        Line.create({
            'partner_id': partner.id,
            'sequence': 10 + index,
            'name': name,
            'value': shape % (number if shape.startswith('+') else handle),
        })
        made += 1
    return made


def load_biography(env):
    """Раздать участникам биографию и способы связи."""
    Partner = env['res.partner'].sudo()
    Education = env['coop.education'].sudo()
    Achievement = env['coop.achievement'].sudo()

    partners = Partner.search([
        ('is_company', '=', False),
        ('id', 'in', env['coop.membership'].sudo().search([]).mapped(
            'partner_id').ids),
    ])
    if not partners:
        _logger.info('Биография: участников не нашлось, пропускаю')
        return 0

    rnd = random.Random(20260904)
    touched = 0
    for partner in partners:
        # Треть страниц оставляем пустыми: пустое состояние должно
        # попадаться при проверке само.
        if rnd.random() < 0.33:
            continue

        if not Education.search_count([('partner_id', '=', partner.id)]):
            for name, speciality, level in rnd.sample(
                    SCHOOLS, k=rnd.randint(1, 3)):
                year_from = rnd.randint(1988, 2018)
                length = {'school': 10, 'college': 3,
                          'higher': 5, 'courses': 1}[level]
                Education.create({
                    'partner_id': partner.id,
                    'name': name,
                    'speciality': speciality,
                    'level': level,
                    'year_from': year_from,
                    'year_to': year_from + length,
                })

        if rnd.random() < 0.6 and not Achievement.search_count(
                [('partner_id', '=', partner.id)]):
            for name, has_proof in rnd.sample(
                    ACHIEVEMENTS, k=rnd.randint(1, 3)):
                Achievement.create({
                    'partner_id': partner.id,
                    'name': name,
                    'year': rnd.randint(2016, 2025),
                    'proof_url': ('https://reestr.cooptech.ru/%s'
                                  % rnd.randint(1000, 9999))
                                 if has_proof else False,
                })

        # Мессенджеры, приложения и Skype больше не поля карточки:
        # человек заводит их сам свободными полями контакта.
        partner.write({'coop_languages': rnd.choice(LANGUAGES)})
        if rnd.random() < 0.75:
            contact_lines(env, partner, rnd)
        touched += 1

    _logger.info('Биография: заполнено у %s участников из %s',
                 touched, len(partners))
    return touched


def age_listings(env):
    """Разнести даты создания объявлений по прошедшему году.

    Каталог, целиком созданный одной минутой, врёт сразу в нескольких
    местах: порядок «сначала новые» ничего не упорядочивает, напоминание
    о залежавшемся объявлении не показать, и не видно, как выглядит
    выдача, где рядом стоят вчерашнее и полугодовой давности.

    Через SQL, потому что `create_date` движок пишет сам и через ORM его
    не задать.
    """
    rnd = random.Random(20260905)
    updated = 0
    for model, table in (('coop.resource', 'coop_resource'),
                         ('coop.skill.offer', 'coop_skill_offer'),
                         ('coop.vacancy', 'coop_vacancy'),
                         ('coop.project', 'coop_project')):
        if model not in env:
            continue
        ids = env[model].sudo().search([]).ids
        if not ids:
            continue
        # Распределение смещено к свежему: старых объявлений в живом
        # каталоге меньше, чем новых, а не поровну.
        pairs = [(rnd.choice([rnd.randint(0, 30), rnd.randint(0, 120),
                              rnd.randint(0, 365)]), record_id)
                 for record_id in ids]
        env.cr.executemany(
            "UPDATE %s SET create_date = now() - (%%s || ' days')::interval "
            "WHERE id = %%s" % table, pairs)
        updated += len(pairs)
    _logger.info('Даты создания разнесены у %s записей', updated)
    return updated


def add_followers(env):
    """Подписчики на страницах участников.

    В макете число подписчиков стоит в строке показателей, и ноль у всех
    подряд читается как неработающий счётчик. Своей модели подписки нет
    — Odoo для этого хранит подписчиков записи, ими же ходит «написать
    участнику».
    """
    Follower = env['mail.followers'].sudo()
    partners = env['res.partner'].sudo().browse(
        env['coop.membership'].sudo().search([]).mapped('partner_id').ids)
    if len(partners) < 5:
        return 0

    rnd = random.Random(20260906)
    ids = partners.ids
    created = 0
    for partner in partners:
        # Подписчики есть не у всех и в разном числе: страница без них
        # тоже должна попасться при проверке.
        if rnd.random() < 0.3:
            continue
        others = rnd.sample(ids, k=min(len(ids), rnd.randint(1, 25)))
        for other_id in others:
            if other_id == partner.id:
                continue
            if Follower.search_count([('res_model', '=', 'res.partner'),
                                      ('res_id', '=', partner.id),
                                      ('partner_id', '=', other_id)]):
                continue
            Follower.create({
                'res_model': 'res.partner',
                'res_id': partner.id,
                'partner_id': other_id,
            })
            created += 1
    _logger.info('Подписок заведено: %s', created)
    return created


def enrich_showcase(env, login='dashkevich'):
    """Добить полосы у страницы, которую смотрят при показе.

    На демонстрации открывают одну и ту же страницу, и половина полос на
    ней пустовала: ни проектов, ни вакансий, ни друзей. Пустая полоса
    прячется целиком, и со стороны кажется, что раздела нет вовсе.

    Записи не выдумываются, а передаются существующие — вместе с
    фотографиями и описаниями: свежесозданные «Проект 1, Проект 2»
    выглядели бы заглушками, а тут человек видит настоящий каталог.
    """
    user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    if not user:
        _logger.info('Витрина: пользователь %s не найден', login)
        return 0
    partner = user.partner_id
    touched = 0

    # ── Проекты ────────────────────────────────────────────────────────
    Project = env['coop.project'].sudo()
    # Добираем до четырёх, а не «если ни одного»: с единственной плиткой
    # полка выглядит остатком, а не разделом, — и показывать на ней
    # нечего, ради чего полка и заведена.
    own_ids = Project.search_count([('partner_id', '=', partner.id)])
    if own_ids < 4:
        # С картинкой и заполненные: полоса плиток без фотографий
        # выглядит сломанной.
        projects = Project.search([('image_512', '!=', False),
                                   ('partner_id', '!=', partner.id)],
                                  limit=4 - own_ids)
        if projects:
            projects.write({'partner_id': partner.id})
            touched += len(projects)

    # ── Вакансии ───────────────────────────────────────────────────────
    Vacancy = env['coop.vacancy'].sudo()
    my_vacancies = Vacancy.search_count([('partner_id', '=', partner.id)])
    if my_vacancies < 4:
        vacancies = Vacancy.search([('state', '=', 'published'),
                                    ('partner_id', '!=', partner.id)],
                                   limit=4 - my_vacancies)
        if vacancies:
            vacancies.write({'partner_id': partner.id})
            touched += len(vacancies)

    # ── Образование ────────────────────────────────────────────────────
    #
    # Все четыре ступени: витринная страница показывает, как блок
    # выглядит заполненным. У Дашкевича было две записи из четырёх, и
    # половина строк блока пустовала.
    Education = env['coop.education'].sudo()
    Institution = env['coop.institution'].sudo()
    exists = set(Education.search(
        [('partner_id', '=', partner.id)]).mapped('level'))
    city = partner.city or ''
    for edu_level, year in (('higher', 2009), ('school', 2004)):
        if edu_level in exists:
            continue
        institution = Institution.search(
            [('kind', '=', edu_level), ('city', '=', city)], limit=1)
        if not institution:
            institution = Institution.search([('kind', '=', edu_level)], limit=1)
        if not institution:
            continue
        with env.cr.savepoint():
            Education.create({
                'partner_id': partner.id,
                'institution_id': institution.id,
                'level': edu_level,
                'year_from': year - 5 if edu_level == 'higher' else year - 11,
                'year_to': year,
                'speciality': ('Электроснабжение' if edu_level == 'higher'
                               else False),
            })
        touched += 1

    # ── Ресурсы ────────────────────────────────────────────────────────
    #
    # Только предложения. Спрос у него есть и живёт в своей полке
    # «Потребности»; полка «Ресурсы» отвечает на другой вопрос — что у
    # человека есть, — и без единого предложения пряталась целиком.
    Resource = env['coop.resource'].sudo()
    own_list = Resource.search_count([('owner_id', '=', partner.id),
                                  ('listing_type', '=', 'offer')])
    if not own_list:
        resources = Resource.search([
            ('listing_type', '=', 'offer'),
            ('state', '=', 'published'),
            ('image_512', '!=', False),
            ('project_id', '=', False),
        ], limit=4)
        if resources:
            resources.write({'owner_id': partner.id})
            touched += len(resources)

    # ── Навыки ─────────────────────────────────────────────────────────
    #
    # Две плитки в полке — это не полка. Витринная страница показывает,
    # как раздел выглядит наполненным, и четырёх хватает, чтобы ряд
    # читался рядом, а не остатком.
    Offer = env['coop.skill.offer'].sudo()
    mine_ids = Offer.search_count([('partner_id', '=', partner.id)])
    if mine_ids < 4:
        skills = Offer.search([
            ('partner_id', '!=', partner.id),
            ('state', '=', 'published'),
            ('image_512', '!=', False),
        ], limit=4 - mine_ids)
        if skills:
            skills.write({'partner_id': partner.id})
            touched += len(skills)

    # ── Друзья ─────────────────────────────────────────────────────────
    #
    # Дружба двусторонняя и лежит отдельной записью, поэтому её нельзя
    # «дописать полем» — заводим настоящие принятые связи.
    Friendship = env['coop.friendship'].sudo()
    existing = Friendship.search_count([
        '|', ('requester_id', '=', partner.id),
        ('addressee_id', '=', partner.id),
        ('state', '=', 'accepted'),
    ])
    if not existing:
        # Только живые участники каталога: служебные записи вроде
        # «Administrator» в друзьях выглядят ошибкой — у них нет ни
        # фотографии, ни страницы, на которую можно перейти.
        service = env['res.users'].sudo().search([
            ('login', 'in', ['admin', '__system__', 'default'])]).mapped(
                'partner_id').ids
        others = env['res.partner'].sudo().search([
            ('id', '!=', partner.id),
            ('id', 'not in', service),
            ('is_company', '=', False),
            ('image_1920', '!=', False),
            ('coop_specialization_id', '!=', False),
            ('id', 'in', env['coop.membership'].sudo().search([]).mapped(
                'partner_id').ids),
        ], limit=6)
        for other in others:
            if Friendship.search_count([
                    '|',
                    '&', ('requester_id', '=', partner.id),
                    ('addressee_id', '=', other.id),
                    '&', ('requester_id', '=', other.id),
                    ('addressee_id', '=', partner.id)]):
                continue
            Friendship.create({
                'requester_id': other.id,
                'addressee_id': partner.id,
                'state': 'accepted',
            })
            touched += 1

    # ── Образование, достижения и связь ────────────────────────────────
    #
    # Обычная раздача биографии витринную страницу обходит стороной: она
    # идёт по тем, у кого есть членство в организации, а владелец стенда
    # числится сам по себе. После пересборки базы это выглядит как
    # пропавший блок — полоса без записей прячется целиком.
    rnd = random.Random(partner.id)

    Education = env['coop.education'].sudo()
    if not Education.search_count([('partner_id', '=', partner.id)]):
        for name, speciality, level in rnd.sample(SCHOOLS, k=2):
            year_from = rnd.randint(1995, 2015)
            length = {'school': 10, 'college': 3,
                      'higher': 5, 'courses': 1}[level]
            Education.create({
                'partner_id': partner.id,
                'name': name,
                'speciality': speciality,
                'level': level,
                'year_from': year_from,
                'year_to': year_from + length,
            })
            touched += 1

    Achievement = env['coop.achievement'].sudo()
    if not Achievement.search_count([('partner_id', '=', partner.id)]):
        for name, has_proof in rnd.sample(ACHIEVEMENTS, k=3):
            Achievement.create({
                'partner_id': partner.id,
                'name': name,
                'year': rnd.randint(2016, 2025),
                'proof_url': ('https://reestr.cooptech.ru/%s'
                              % rnd.randint(1000, 9999)) if has_proof else False,
            })
            touched += 1

    # Способы связи: без них колонка «Контакты» пуста, а в макете она
    # стоит первой, и пустой читается как поломка, а не как выбор.
    if not partner.coop_languages:
        partner.write({'coop_languages': rnd.choice(LANGUAGES)})
        touched += 1
    touched += contact_lines(env, partner, rnd, count=2)

    _logger.info('Витрина: дополнено записей — %s', touched)
    return touched

def link_education(env):
    """Привязать записи об образовании к справочнику заведений.

    Записи заводились свободной строкой, до появления справочника: 306
    строк вроде «Политехнический колледж №8». Сокращения у них нет, а
    владелец 15 сентября 2026 велел показывать именно сокращённое —
    «СФУ», «ИФКАТТ».

    Сначала ищем заведение по названию: часть строк совпадёт дословно.
    Остальным подбираем по городу участника и ступени записи — на
    демонстрации важно, чтобы у сибиряка в графе стоял сибирский вуз, а
    не первый попавшийся.

    Безвредно при повторе: записи с уже проставленным заведением
    пропускаются.
    """
    Institution = env['coop.institution'].sudo()
    Education = env['coop.education'].sudo()
    reference = Institution.search([])
    if not reference:
        _logger.info('Образование: справочник заведений пуст')
        return 0

    by_title = {(entry.name or '').strip().lower(): entry for entry in reference}
    by_city = {}
    for entry in reference:
        by_city.setdefault((entry.city or '', entry.kind), []).append(entry)
    by_level = {}
    for entry in reference:
        by_level.setdefault(entry.kind, []).append(entry)

    rnd = random.Random(20260915)
    linked_count = 0
    for record in Education.search([('institution_id', '=', False)]):
        found = by_title.get((record.name or '').strip().lower())
        if not found:
            city = record.partner_id.city or ''
            own_list = by_city.get((city, record.level)) or []
            if_none = by_level.get(record.level) or []
            set_of = own_list or if_none
            if not set_of:
                continue
            # Выбор по номеру записи, а не наугад: повторный прогон
            # наполнения должен дать то же самое, иначе каталог меняется
            # на ровном месте.
            found = set_of[record.id % len(set_of)]
        with env.cr.savepoint():
            record.write({'institution_id': found.id, 'name': False})
        linked_count += 1

    _logger.info('Образование: привязано к справочнику %s записей', linked_count)
    return linked_count
