# -*- coding: utf-8 -*-
"""Опросы и отложенные записи на стенах (решения 404, 410).

Каталог наполняется не менее чем сотней-двумя примеров: на пяти опросах
не видно ни анонимного и открытого рядом, ни завершённого, ни опроса без
единого голоса, ни полосы в девяносто процентов. Здесь около ста
шестидесяти опросов и несколько тысяч голосов.

Раскладка неровная, как в жизни:
- стены людей, организаций, сообществ и проектов;
- без срока, со сроком впереди, завершённые по сроку и автором;
- анонимные и открытые (открытых около трети);
- голосов от нуля до сотни с лишним; у одного варианта бывает почти всё;
- главный участник витрины — автор нескольких опросов на своей стене и
  участник части чужих; в остальных он ещё не голосовал.

Голоса пишутся тем же путём, что и из браузера (`_coop_cast`), —
журналом с номерами и хэшами, по порядку времени.

Отложенные записи — около ста двадцати, у людей с учётной записью: до
выхода их видит только автор. Заводятся от имени автора — иначе «Отправить
сейчас» ему было бы нельзя, а выпускал бы их крон не от его имени.

Даты записей-опросов — позже последней записи загрузчика на той же
стене: лента подгружается по номеру записи, и опрос с номером больше
соседей, но датой раньше, встал бы не на своё место
(`load_wall_posts._order_walls`).

Повторный запуск ничего не добавляет: опросы уже есть — ничего не делается.
"""
import logging
import random
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

TEST_NAMES = ('Danil', 'Proverka Vyhoda')

# Вопрос и варианты. Без рода в глаголах: голосуют и мужчины, и женщины.
PEOPLE_POLLS = [
    ('Когда удобнее созвониться по совместному заказу?',
     ['Утром до десяти', 'В обед', 'Вечером после шести', 'В выходные']),
    ('Какой способ расчёта предпочитаете в сделках со мной?',
     ['Рубли', 'Токены КООП', 'Зачёт встречных услуг', 'Без разницы']),
    ('Делать ли мастер-класс по своей специальности?',
     ['Да, очно', 'Да, онлайн', 'Лучше видеозаписью', 'Не интересно']),
    ('Что выложить следующим?',
     ['Фото готовых работ', 'Разбор ошибок', 'Прайс', 'Отзывы заказчиков']),
    ('Какой срок выполнения заказа для вас нормальный?',
     ['До недели', 'Две недели', 'Месяц', 'Главное — качество']),
    ('Берёте инструмент в аренду у соседей по платформе?',
     ['Регулярно', 'Иногда', 'Пока нет, но хочу', 'Нет']),
    ('Нужна ли совместная закупка материалов на следующий месяц?',
     ['Да, участвую', 'Да, если скидка от 15%', 'Нет']),
    ('Как узнали о платформе?',
     ['От друзей', 'Через кооператив', 'Из соцсетей', 'На выставке', 'Другое']),
    ('Какой формат встречи участников удобнее?',
     ['Очно в городе', 'Онлайн', 'Смешанный']),
    ('Стоит ли вводить предоплату за крупные заказы?',
     ['Да, 30%', 'Да, 50%', 'Нет, оплата по факту']),
    ('Что важнее при выборе исполнителя?',
     ['Уровень доверия', 'Цена', 'Сроки', 'Фото работ', 'Отзывы']),
    ('Нужен ли общий чат мастеров города?',
     ['Да', 'Нет', 'Есть уже, дайте ссылку']),
]

ORG_POLLS = [
    ('Когда провести общее собрание пайщиков?',
     ['В последнюю пятницу месяца', 'В первую субботу', 'Онлайн в будний вечер']),
    ('Куда направить часть прибыли квартала?',
     ['В неделимый фонд', 'На обучение', 'На новое оборудование',
      'Распределить по паям']),
    ('Запускать ли доставку по области?',
     ['Да, своими силами', 'Да, через партнёров', 'Пока рано']),
    ('Какой продукт добавить в ассортимент?',
     ['Сезонные наборы', 'Полуфабрикаты', 'Подарочные корзины',
      'Продукцию соседей по кооперативу']),
    ('Вступать ли в союз кооперативов региона?',
     ['Да', 'Нет', 'Сначала изучить условия']),
    ('Какой режим работы склада удобнее?',
     ['С 8 до 17', 'С 10 до 19', 'Круглосуточно по записи']),
    ('Нужна ли своя касса взаимопомощи?',
     ['Да', 'Нет', 'Обсудить на собрании']),
    ('Принимать ли оплату токенами КООП?',
     ['Да, полностью', 'Да, до 30% суммы', 'Нет']),
    ('Где открыть вторую точку?',
     ['В центре', 'В спальном районе', 'В соседнем городе', 'Пока не открывать']),
]

COMMUNITY_POLLS = [
    ('Тема следующей встречи сообщества?',
     ['Налоги самозанятых', 'Поиск заказчиков', 'Совместные закупки',
      'Обмен опытом']),
    ('Как часто встречаться?',
     ['Раз в неделю', 'Раз в две недели', 'Раз в месяц']),
    ('Нужны ли правила публикаций в сообществе?',
     ['Да, строгие', 'Да, простые', 'Нет']),
    ('Где искать площадку для встреч?',
     ['Библиотека', 'Коворкинг', 'Помещение кооператива', 'Онлайн']),
]

PROJECT_POLLS = [
    ('Какой этап проекта сделать первым?',
     ['Проектирование', 'Закупка материалов', 'Сбор команды']),
    ('Нужно ли расширить сбор вкладов?',
     ['Да, на 20%', 'Да, вдвое', 'Нет, уложимся']),
    ('Как отчитываться о ходе проекта?',
     ['Каждую неделю', 'По вехам', 'Раз в месяц']),
    ('Подключать ли внешнего подрядчика?',
     ['Да', 'Нет, своими силами', 'Только на сложные работы']),
]

SCHEDULED_TEXTS = [
    'Завтра открываем запись на следующий месяц — места ограничены.',
    'Напоминание: общее собрание в пятницу, повестка в документах.',
    'Скоро выложу фото с объекта — следите за лентой.',
    'Новый прайс вступает в силу с первого числа.',
    'Прямой эфир о работе кооператива — в четверг вечером.',
    'Итоги месяца: что сделано и что впереди.',
    'Поздравляю всех с профессиональным праздником!',
    'Начинаем совместную закупку — пишите, кто участвует.',
    'Отчёт о ходе проекта — первая веха пройдена.',
    'Выставка работ участников — приходите в субботу.',
]


def _weights(rnd, n):
    """Доли вариантов: иногда почти единодушно, иногда поровну."""
    mood = rnd.random()
    if mood < 0.2:
        lead = rnd.randrange(n)
        return [8 if i == lead else 1 for i in range(n)]
    if mood < 0.5:
        return [1] * n
    return [rnd.uniform(0.3, 3) for _ in range(n)]


def _vote_count(rnd, people):
    roll = rnd.random()
    if roll < 0.08:
        return 0
    if roll < 0.35:
        return rnd.randint(1, 6)
    if roll < 0.8:
        return rnd.randint(7, 40)
    return rnd.randint(41, min(130, len(people)))


def load_wall_polls(env, login='dashkevich'):
    if 'coop.wall.poll' not in env:
        return 0
    Poll = env['coop.wall.poll'].sudo()
    Vote = env['coop.wall.poll.vote'].sudo()
    Message = env['mail.message'].sudo()
    Partner = env['res.partner'].sudo()
    if Poll.search_count([], limit=1):
        _logger.info('Опросы на стенах: уже наполнено, пропускаю')
        return 0
    rnd = random.Random(20260924 + 410)
    now = datetime.now().replace(microsecond=0)
    comment = env.ref('mail.mt_comment')

    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('name', 'not in', TEST_NAMES),
    ])
    orgs = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True),
    ])
    if len(people) < 20:
        _logger.info('Опросы на стенах: нечего наполнять')
        return 0
    showcase = env['res.users'].sudo().search(
        [('login', '=', login)], limit=1).partner_id

    # Самая поздняя запись загрузчика на каждой стене — см. строку модуля.
    latest = {}
    for model, res_id, date in Message._read_group(
            [('model', 'in', ('res.partner', 'coop.project', 'coop.community')),
             ('message_type', '=', 'comment')],
            ['model', 'res_id'], ['date:max']):
        latest[(model, res_id)] = date

    # Стены: (модель, запись, автор опроса, набор вопросов).
    walls = []
    for page in rnd.sample(list(people), k=min(70, len(people))):
        walls.append(('res.partner', page, page, PEOPLE_POLLS))
    for org in rnd.sample(list(orgs), k=min(40, len(orgs))):
        members = org.coop_member_ids.filtered(
            lambda m: m.state == 'active').partner_id if 'coop_member_ids' in org else Partner
        walls.append(('res.partner', org, members[:1] or org, ORG_POLLS))
    if 'coop.community' in env:
        for community in rnd.sample(list(env['coop.community'].sudo().search([])),
                                    k=min(25, env['coop.community'].sudo().search_count([]))):
            author = community.partner_id or rnd.choice(people)
            walls.append(('coop.community', community, author, COMMUNITY_POLLS))
    if 'coop.project' in env:
        projects = env['coop.project'].sudo().search([])
        for project in rnd.sample(list(projects), k=min(20, len(projects))):
            author = project.partner_id or project.author_id or rnd.choice(people)
            walls.append(('coop.project', project, author, PROJECT_POLLS))
    if showcase:
        for _n in range(6):
            walls.append(('res.partner', showcase, showcase, PEOPLE_POLLS))

    made = votes_made = 0
    used_questions = {}
    for model, record, author, pool in walls:
        start = latest.get((model, record.id)) or (now - timedelta(days=60))
        start = max(start, now - timedelta(days=60))
        if now - start < timedelta(hours=3):
            start = now - timedelta(hours=rnd.randint(3, 30))
        # Вопрос на одной стене не повторяется.
        seen = used_questions.setdefault((model, record.id), set())
        choices = [q for q in pool if q[0] not in seen] or pool
        question, options = rnd.choice(choices)
        seen.add(question)
        posted = start + (now - start) * rnd.uniform(0.1, 0.95)
        posted = posted.replace(microsecond=0)

        # Срок: без срока, впереди, уже прошёл; иногда закрыт автором.
        roll = rnd.random()
        close_at = False
        closed_manually = False
        if roll < 0.35:
            close_at = now + timedelta(days=rnd.randint(1, 20), hours=rnd.randint(0, 23))
        elif roll < 0.6 and now - posted > timedelta(days=2):
            close_at = posted + (now - posted) * rnd.uniform(0.3, 0.9)
            close_at = close_at.replace(microsecond=0)
        elif roll < 0.68:
            closed_manually = True

        message = Message.create({
            'model': model,
            'res_id': record.id,
            'message_type': 'comment',
            'subtype_id': comment.id,
            'author_id': author.id,
            'body': '',
            'date': posted,
        })
        poll = Poll.create({
            'message_id': message.id,
            'author_id': author.id,
            'question': question,
            'is_public': rnd.random() < 0.33,
            'close_at': close_at,
            'closed_manually': closed_manually,
            'option_ids': [(0, 0, {'name': name, 'sequence': i})
                           for i, name in enumerate(options)],
        })
        made += 1

        # Голоса — по порядку времени, между публикацией и концом опроса.
        end = min(close_at or now, now)
        voters = rnd.sample(list(people), k=_vote_count(rnd, people))
        if showcase and author != showcase and showcase not in voters \
                and rnd.random() < 0.3:
            voters.append(showcase)
        if showcase and author == showcase:
            # На своей стене витрины: в части опросов свой голос есть,
            # в части — нет, чтобы было видно оба состояния.
            voters = [v for v in voters if v != showcase]
            if rnd.random() < 0.5:
                voters.append(showcase)
        weights = _weights(rnd, len(options))
        stamps = sorted(posted + (end - posted) * rnd.uniform(0.01, 0.99)
                        for _v in voters)
        for voter, stamp in zip(voters, stamps):
            option = rnd.choices(poll.option_ids, weights=weights)[0]
            Vote._coop_cast(poll, option, voter, date=stamp.replace(microsecond=0))
            votes_made += 1

    _logger.info('Опросы на стенах: %s опросов, %s голосов', made, votes_made)
    return made


def load_wall_scheduled(env, login='dashkevich'):
    """Отложенные записи — у людей с учётной записью, от их имени."""
    if 'coop.wall.poll' not in env:
        return 0
    Scheduled = env['mail.scheduled.message'].sudo()
    walls = ('res.partner', 'coop.project', 'coop.community')
    if Scheduled.search_count([('model', 'in', walls)], limit=1):
        _logger.info('Отложенные записи: уже наполнено, пропускаю')
        return 0
    rnd = random.Random(20260924 + 4101)
    now = datetime.now().replace(microsecond=0)
    users = env['res.users'].sudo().search([
        ('share', '=', False),
        ('partner_id.coop_is_participant', '=', True),
        ('partner_id.is_company', '=', False),
        ('partner_id.name', 'not in', TEST_NAMES),
    ])
    showcase = users.filtered(lambda u: u.login == login)
    made = 0
    authors = list(users - showcase)
    rnd.shuffle(authors)
    plan = [(showcase, n) for n in range(5)] if showcase else []
    plan += [(u, 0) for u in authors[:115]]
    for user, n in plan:
        at = now + timedelta(days=rnd.randint(0, 40), hours=rnd.randint(1, 23),
                             minutes=rnd.choice((0, 15, 30, 45)))
        partner = user.partner_id
        env_user = env(user=user)
        if showcase and user == showcase and n == 4:
            # Один отложенный опрос у витрины — как выглядит опрос до выхода.
            env_user['coop.wall.poll'].coop_create(
                'res.partner', partner.id, 'Что обсудить на встрече мастеров?',
                ['Цены на услуги', 'Совместные закупки', 'Обучение новичков'],
                False, False, at.strftime('%Y-%m-%d %H:%M:%S'))
        else:
            env_user['mail.scheduled.message'].create({
                'model': 'res.partner',
                'res_id': partner.id,
                'author_id': partner.id,
                'body': '<p>%s</p>' % rnd.choice(SCHEDULED_TEXTS),
                'scheduled_date': at,
            })
        made += 1
    _logger.info('Отложенные записи: %s', made)
    return made
