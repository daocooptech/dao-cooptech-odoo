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

MESSENGERS = ['Telegram', 'Telegram, WhatsApp', 'WhatsApp, Viber',
              'Telegram, Viber', 'Telegram, WhatsApp, Viber']

APPS = ['GitHub', 'GitHub, Habr', 'Habr', 'Дзен', 'GitHub, Хабр, Дзен']


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

        values = {'coop_languages': rnd.choice(LANGUAGES)}
        if rnd.random() < 0.7:
            values['coop_messengers'] = rnd.choice(MESSENGERS)
        if rnd.random() < 0.3:
            values['coop_apps'] = rnd.choice(APPS)
        if rnd.random() < 0.25:
            values['coop_skype'] = 'coop-%s' % partner.id
        partner.write(values)
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
    if not Project.search_count([('partner_id', '=', partner.id)]):
        # С картинкой и заполненные: полоса плиток без фотографий
        # выглядит сломанной.
        projects = Project.search([('image_512', '!=', False)], limit=4)
        if projects:
            projects.write({'partner_id': partner.id})
            touched += len(projects)

    # ── Вакансии ───────────────────────────────────────────────────────
    Vacancy = env['coop.vacancy'].sudo()
    if not Vacancy.search_count([('partner_id', '=', partner.id)]):
        vacancies = Vacancy.search([('state', '=', 'published')], limit=3)
        if vacancies:
            vacancies.write({'partner_id': partner.id})
            touched += len(vacancies)

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

    _logger.info('Витрина: дополнено записей — %s', touched)
    return touched
