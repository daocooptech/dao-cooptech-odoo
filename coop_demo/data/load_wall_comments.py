# -*- coding: utf-8 -*-
"""Комментарии к записям на стенах (решение 404).

Каталог наполняется не менее чем сотней-двумя примеров: на пяти
комментариях не видно ни «Показать все», ни длинной ветки, ни записи
без единого отклика. Здесь около трёхсот.

Раскладка неровная, как в жизни: у большинства записей комментариев
нет; у части — один-два; у витринных записей главного участника — ветки
до семи, чтобы было что раскрывать. Автор записи иногда отвечает в своей
ветке. Комментаторы — участники платформы, без тестовых учёток; даты —
после записи и не позже сегодняшнего дня. Тексты без рода в глаголах:
среди комментаторов и мужчины, и женщины.

Повторный запуск ничего не добавляет: если комментарии уже есть,
загрузчик не делает ничего. Пропускать только записи с комментариями
было мало — каждый прогон заново бросал жребий по записям без них, и
24 сентября второй прогон удвоил наполнение.
"""
import logging
import random
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

REPLIES = [
    'Отличная работа, аккуратно сделано.',
    'Сколько по времени заняло?',
    'А по цене сориентируете? Напишу в сообщения.',
    'Сохранено в избранное — пригодится.',
    'Интересно. Есть фото поближе?',
    'Поддерживаю! Если нужна помощь — пишите.',
    'Было бы здорово повторить такое у нас в городе.',
    'Спасибо, что делитесь опытом.',
    'Можно ли присоединиться к следующему заказу?',
    'Беру на заметку, как раз ищем исполнителя.',
    'А материалы свои или заказчика?',
    'Рекомендую — работали вместе, всё в срок.',
    'Сроки реальные? Нам нужно к концу месяца.',
    'Хорошая новость, поздравляю!',
    'Есть вопрос по гарантии — напишу лично.',
    'Подписка оформлена, жду продолжения.',
    'С ценой поспорю, но качество видно.',
    'А доставка до области возможна?',
    'Ещё актуально?',
    'Можно контакт того, кто делал проект?',
    'Отзыв оставлен, всё прошло отлично.',
    'Держите в курсе, интересно, чем закончится.',
    'Такое бы в общий фонд кооператива — многим нужно.',
    'Вопрос снят, нашёлся ответ в документах.',
]

AUTHOR_REPLIES = [
    'Спасибо!',
    'Да, актуально — пишите в сообщения.',
    'Около недели, если без переделок.',
    'Материалы мои, в цену входят.',
    'Доставка есть, по области — отдельно.',
    'Фото добавлено в ресурсы на странице.',
    'Спасибо за отзыв, рады стараться.',
]

TEST_NAMES = ('Danil', 'Proverka Vyhoda')


def load_wall_comments(env, login='dashkevich'):
    Comment = env['coop.wall.comment'].sudo()
    Message = env['mail.message'].sudo()
    Partner = env['res.partner'].sudo()
    rnd = random.Random(20260924 + 404)
    now = datetime.now()

    posts = Message.search([
        ('model', '=', 'res.partner'), ('message_type', '=', 'comment'),
        ('subtype_id.internal', '=', False),
    ], order='date desc, id desc')
    if Comment.search_count([], limit=1):
        _logger.info("Комментарии к стенам: уже наполнено, пропускаю")
        return 0
    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('name', 'not in', TEST_NAMES),
    ])
    if not posts or len(people) < 10:
        _logger.info("Комментарии к стенам: нечего наполнять")
        return 0

    showcase = env['res.users'].sudo().search(
        [('login', '=', login)], limit=1).partner_id

    rows = []
    for post in posts:
        mine = showcase and post.res_id == showcase.id
        if mine:
            count = rnd.choice((0, 2, 3, 4, 5, 7))
        else:
            # Большинство записей — без комментариев.
            roll = rnd.random()
            count = 0 if roll < 0.87 else (1 if roll < 0.94 else rnd.randint(2, 4))
        if not count:
            continue
        # Время комментариев — между записью и сегодняшним днём, не дальше
        # десяти дней от записи. Шагами от записи вперёд было нельзя: у
        # свежей записи шаги упирались в «сейчас», и вся ветка получала
        # одно и то же время.
        start = post.date or now
        window = min(now - start, timedelta(days=10))
        if window <= timedelta(minutes=10):
            continue
        offsets = sorted(rnd.uniform(0.02, 1.0) for _n in range(count))
        for n, share in enumerate(offsets):
            when = start + window * share
            author_answers = n > 0 and post.author_id and rnd.random() < 0.2
            if author_answers:
                author = post.author_id
                body = rnd.choice(AUTHOR_REPLIES)
            else:
                author = rnd.choice(people)
                while author == post.author_id:
                    author = rnd.choice(people)
                body = rnd.choice(REPLIES)
            rows.append({
                'post_id': post.id,
                'author_id': author.id,
                'body': body,
                'date': when,
            })
    if rows:
        Comment.create(rows)
    _logger.info("Комментарии к стенам: заведено %s", len(rows))
    return len(rows)
