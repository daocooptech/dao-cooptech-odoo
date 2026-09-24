# -*- coding: utf-8 -*-
"""Записи на стенах людей и организаций — для лент подписок (решение 65).

У каждого каталога своя лента подписок, и новость человека или
организации — запись на стене их страницы. На боевой 24 сентября 2026
таких записей была одна на всю платформу: ленты людей и организаций
открывались бы пустыми.

Тексты — по делу и от первого лица, с профессией и городом, без рода в
глаголах: «сдан заказ», а не «закончил» — среди авторов и мужчины, и
женщины. Записи заводятся прямо сообщениями, минуя рассылку: тысяча
уведомлений подписчикам разом — не то, ради чего наполняется витрина.

Повторный запуск ничего не удваивает: страница, где уже есть запись,
пропускается.
"""
import logging
import random
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

PEOPLE = [
    'Сдан заказ — {spec}. Спасибо заказчику из {city} за терпение и точное задание.',
    'Беру заказы на следующий месяц: {spec}, по {city} и области. Пишите в сообщения.',
    'Ищу напарника на объект — работы на две недели. Нужен человек, который знает дело.',
    'Меняю работу на материалы: {spec} в обмен на пиломатериал, краску или инструмент.',
    'Отдам даром остатки после прошлого заказа. Самовывоз, {city}.',
    'Личность подтверждена — в сделках со мной теперь меньше лишних вопросов.',
    'Могу вложиться трудом в проект, если нужен {spec} на несколько смен.',
    'Первый месяц на платформе: три сделки, два отзыва «отлично». Спасибо всем, кто доверился.',
    'Поделюсь опытом с начинающими: {spec} — дело, где мелочей не бывает. Задавайте вопросы.',
    'Свободна неделя в конце месяца — возьму срочный заказ.',
    'Выложены фотографии последних работ — смотрите в ресурсах на странице.',
    'Нужен совет: кто в {city} закупает материалы вскладчину? Хочется присоединиться.',
]

ORGS = [
    'Открыт набор в команду: ищем людей, условия — на странице вакансий.',
    'Новая поставка на склад в {city}. Кто брал в прошлый раз — цена та же.',
    'Итоги квартала: оборот вырос, часть прибыли пойдёт в общий фонд.',
    'Ищем поставщика сырья с доставкой до {city}. Предложения — в сообщения.',
    'Общее собрание — в последнюю пятницу месяца. Повестка — в документах.',
    'Запустили новую линию. Первые заказы — со скидкой для членов кооператива.',
    'Приглашаем к совместной закупке: чем больше участников, тем ниже цена.',
    'Наши работы — на выставке в {city}. Приходите, покажем вживую.',
    'Приняли троих новых пайщиков. Добро пожаловать!',
    'Обновили прайс на услуги — смотрите в ресурсах организации.',
]


def _fill(template, page):
    spec = (page.coop_specialization_id.name or 'мастер на все руки').lower()
    return template.format(spec=spec, city=page.city or 'городе')


def load_wall_posts(env, login='dashkevich'):
    Message = env['mail.message'].sudo()
    Partner = env['res.partner'].sudo()
    comment = env.ref('mail.mt_comment')
    rnd = random.Random(20260924)
    now = datetime.now()

    walled = set(Message.search([
        ('model', '=', 'res.partner'), ('message_type', '=', 'comment'),
    ]).mapped('res_id'))

    rows = []
    for companies, texts, share, per_page in (
            (False, PEOPLE, 0.6, (1, 2)), (True, ORGS, 0.8, (1, 3))):
        pages = Partner.search([
            ('coop_is_participant', '=', True),
            ('is_company', '=', companies),
        ], order='id')
        for page in pages:
            if page.id in walled or rnd.random() > share:
                continue
            for _n in range(rnd.randint(*per_page)):
                when = now - timedelta(days=rnd.randint(1, 120),
                                       hours=rnd.randint(0, 12),
                                       minutes=rnd.randint(0, 59))
                rows.append({
                    'model': 'res.partner',
                    'res_id': page.id,
                    'message_type': 'comment',
                    'subtype_id': comment.id,
                    'author_id': page.id,
                    'body': '<p>%s</p>' % _fill(rnd.choice(texts), page),
                    'date': when,
                })
    # Своя стена главного участника витрины. Общий проход её пропускал:
    # на ней уже была одна запись — проверочная «123» самого владельца, —
    # и страница, которую открывают первой, оставалась почти пустой.
    # Владелец 24 сентября 2026: «на моей странице внизу лента и там
    # только моя запись 123». Своё не трогаем, дописываем до восьми.
    showcase_page = env['res.users'].sudo().search(
        [('login', '=', login)], limit=1).partner_id
    if showcase_page:
        have = Message.search_count([
            ('model', '=', 'res.partner'), ('res_id', '=', showcase_page.id),
            ('message_type', '=', 'comment')])
        if have < 6:
            for template in rnd.sample(PEOPLE, k=min(8 - have, len(PEOPLE))):
                when = now - timedelta(days=rnd.randint(1, 120),
                                       hours=rnd.randint(0, 12))
                rows.append({
                    'model': 'res.partner',
                    'res_id': showcase_page.id,
                    'message_type': 'comment',
                    'subtype_id': comment.id,
                    'author_id': showcase_page.id,
                    'body': '<p>%s</p>' % _fill(template, showcase_page),
                    'date': when,
                })

    # По порядку дат: лента показывает записи по номеру, а не по дате, и
    # заведённые вразнобой шли на стене как «29 мая, 6 сентября, 12 июля».
    rows.sort(key=lambda row: row['date'])
    if rows:
        Message.create(rows)
    _order_walls(env)

    # Главный участник витрины — подписчик организаций со стенами: на
    # людей он подписан загрузчиком страниц (`add_followers`), на
    # организации — нет, и лента организаций у него была бы пустой.
    showcase = env['res.users'].sudo().search(
        [('login', '=', login)], limit=1).partner_id
    followed = 0
    if showcase:
        Follower = env['mail.followers'].sudo()
        have = set(Follower.search([
            ('partner_id', '=', showcase.id), ('res_model', '=', 'res.partner'),
        ]).mapped('res_id'))
        orgs = Partner.search([('coop_is_participant', '=', True),
                               ('is_company', '=', True)])
        with_wall = set(Message.search([
            ('model', '=', 'res.partner'), ('res_id', 'in', orgs.ids),
            ('message_type', '=', 'comment'),
        ]).mapped('res_id'))
        new = [{'res_model': 'res.partner', 'res_id': org_id,
                'partner_id': showcase.id}
               for org_id in sorted(with_wall - have)]
        if new:
            Follower.create(new)
        followed = len(new)

    _logger.info('Стены: записей %s, подписок на организации %s',
                 len(rows), followed)
    return len(rows)


def _order_walls(env):
    """Выровнять даты записей загрузчика с их номерами на каждой стене.

    Лента стены идёт по номеру записи, и первые записи загрузчика,
    заведённые с датами вразнобой, стояли не по времени. Переставляются
    только даты записей самого загрузчика (заведены от имени системы);
    записи людей — как проверочная «123» владельца — не трогаются.
    Повторный запуск ничего не меняет: где порядок верный, писать нечего.
    """
    Message = env['mail.message'].sudo()
    system = (env.ref('base.user_root') | env.ref('base.user_admin')).ids
    posts = Message.search([
        ('model', '=', 'res.partner'), ('message_type', '=', 'comment'),
        ('create_uid', 'in', system),
    ], order='res_id, id')
    fixed = 0
    by_page = {}
    for post in posts:
        by_page.setdefault(post.res_id, []).append(post)
    for page_posts in by_page.values():
        dates = sorted(p.date for p in page_posts)
        for post, date in zip(page_posts, dates):
            if post.date != date:
                post.date = date
                fixed += 1
    if fixed:
        _logger.info('Стены: даты выровнены у %s записей', fixed)
