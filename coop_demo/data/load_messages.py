# -*- coding: utf-8 -*-
"""Переписки раздела «Сообщения».

Каталог из пяти диалогов ничего не показывает: на нём не видно ни
фильтров по видам, ни поиска, ни того, как список ведёт себя, когда
переписок полторы сотни и половину из них человек не помнит по названию.
Поэтому здесь полный набор — личные беседы, торг по сделкам, обсуждения
проектов, чаты организаций и сообществ, служебные уведомления.

Состояния тоже разные, и это главное: есть непрочитанные, есть
закреплённые, есть заглохшие полгода назад, есть заведённые вчера и
пустые. По ним и проверяется экран — по пустой переписке видно, что
показывает лента без сообщений, по заглохшей — что пишется в колонке
времени, когда последнее сообщение старше года.

Все переписки заводятся с участием того, кто смотрит стенд: список
показывает только свои разговоры, и без этого раздел был бы пуст при
полной базе.
"""
import logging
import random

from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

# ── Реплики ──────────────────────────────────────────────────────────
#
# Разговоры собираются из кусочков по видам: в чате организации говорят о
# собраниях и взносах, в сделке — о сроках и оплате, в личной беседе — о
# делах. Один общий набор фраз выдал бы себя сразу: все переписки стали бы
# на одно лицо.
TALK = {
    'org': [
        'Здравствуйте! Подскажите, когда ближайшее общее собрание?',
        'Протокол разослали всем пайщикам, посмотрите почту.',
        'Взнос за квартал приняли, спасибо.',
        'Нужна помощь на складе в субботу, кто может подъехать?',
        'Подготовили смету на ремонт кровли, обсудим на правлении.',
        'Приняли двух новых пайщиков, состав обновлён.',
        'Заявку в реестр подали, ждём ответа.',
        'Отчётность за год сдали без замечаний.',
        'Кто отвечает за закупку кормов в этом сезоне?',
        'Договорились с поставщиком о рассрочке на три месяца.',
    ],
    'deal': [
        'Добрый день! Подтверждаете объём и сроки?',
        'Готовы отгрузить на следующей неделе.',
        'Оплату отправил, проверьте поступление.',
        'Нужен акт приёмки, пришлите форму.',
        'Можем сдвинуть отгрузку на три дня?',
        'Товар принят, замечаний нет.',
        'Приложил фотографии партии.',
        'Цену согласовали, оформляю сделку.',
        'Транспорт заказан на четверг, водитель позвонит.',
        'Часть партии придёт позже, предупреждаю заранее.',
    ],
    'project': [
        'Собираемся в четверг, обсудим этап.',
        'Смету обновил, посмотрите второй лист.',
        'Материалы завезли, можно начинать.',
        'Нужен ещё один сварщик на две недели.',
        'Фотоотчёт по фундаменту выложил.',
        'Сроки сдвигаются на неделю из-за погоды.',
        'Долю участия пересчитали, всем разослал.',
        'Заявку на грант подали, ответ в конце месяца.',
        'Первый прототип собрали, работает.',
        'Кто возьмёт на себя закупку крепежа?',
    ],
    'community': [
        'Всем привет! Встречаемся в субботу на площадке.',
        'Выложил запись прошлой встречи.',
        'Ищем помещение под мастерскую, есть варианты?',
        'Обсуждаем правила приёма новых участников.',
        'Скинулись на инструмент, отчёт по расходам внутри.',
        'Кто едет на форум в следующем месяце?',
        'Подготовили подборку по теме, ссылки в закреплённом.',
        'Провели субботник, спасибо всем, кто пришёл.',
        'Нужны руки на разгрузку в воскресенье.',
        'Есть идея совместной закупки, обсудим?',
    ],
    'person': [
        'Здравствуйте! Видел ваше объявление, ещё актуально?',
        'Да, всё в силе. Когда вам удобно посмотреть?',
        'Могу подъехать в выходные, ближе к обеду.',
        'Хорошо, договорились. Адрес пришлю в сообщении.',
        'Спасибо за помощь вчера, выручили.',
        'Обращайтесь, если что — я рядом.',
        'Подскажете, где брали материал?',
        'Скинул контакты, там дешевле выходит.',
        'По срокам всё в порядке, укладываемся.',
        'Давайте созвонимся завтра после обеда.',
    ],
    'service': [
        'Ваше объявление прошло проверку и опубликовано.',
        'Ступень подтверждения повышена до второй.',
        'По сделке открыт спор, требуется ваше пояснение.',
        'Начислено вознаграждение за выполненную задачу.',
        'Заявка на членство рассмотрена и одобрена.',
        'Срок публикации объявления истекает через три дня.',
        'Изменены правила раздела «Ресурсы», прочитайте.',
        'Ваш кошелёк пополнен, операция подтверждена.',
    ],
}

# Служебные переписки платформы: их заводит не человек, а раздел.
SERVICE_CHANNELS = [
    ('Проверка объявлений', 'Модерация каталогов'),
    ('Подтверждение личности', 'Служба верификации'),
    ('Споры по сделкам', 'Арбитраж платформы'),
    ('Кошелёк и платежи', 'Уведомления по операциям'),
    ('Задачи и вознаграждения', 'Биржа задач'),
    ('Новости платформы', 'ДАО КООПТЕХ'),
]


def _post(channel, author, body, when):
    """Сообщение в переписку — задним числом и без рассылки.

    `message_post` шлёт уведомления и пишет в шину: на девятистах
    сообщениях загрузки это минуты ожидания и почтовая очередь в
    несколько тысяч писем. Здесь нужен только след разговора, поэтому
    запись создаётся напрямую, а дата ставится сразу нужная — иначе все
    полторы сотни переписок оказались бы «сегодня в 12:00», и колонка
    времени в списке ничего бы не показывала.
    """
    env = channel.env
    message = env['mail.message'].sudo().create({
        'model': 'discuss.channel',
        'res_id': channel.id,
        'message_type': 'comment',
        'subtype_id': env.ref('mail.mt_comment').id,
        'body': '<p>%s</p>' % body,
        'author_id': author.id,
        'date': when,
    })
    return message


def _channel(env, name, kind, partners, self_partner, as_user,
             subtitle=False, res_model=False, res_id=False, pinned=False):
    """Канал с составом. Себя добавляем всегда — иначе он не наш.

    Состав передаётся командами «добавить», а не «заменить»: движок
    разбирает список участников сам и с командой замены складывает в
    набор идентификаторов вложенный список — падает на первом же канале.

    Заводится от имени того, чьи это переписки. Движок молча дописывает в
    состав того, кто создаёт канал, и при загрузке из-под администратора
    в каждой личной беседе оказывался третий — а личная беседа втроём не
    бывает, и создание падало на проверке состава.
    """
    members = self_partner | partners
    return env['discuss.channel'].with_user(as_user).sudo().create({
        'name': name,
        'channel_type': 'group' if len(members) > 2 else 'chat',
        'channel_partner_ids': [(4, pid) for pid in members.ids],
        'coop_kind': kind,
        'coop_subtitle': subtitle,
        'coop_res_model': res_model,
        'coop_res_id': res_id,
        'coop_pinned': pinned,
    })


def load_messages(env, login='dashkevich'):
    user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    if not user:
        user = env.ref('base.user_admin', raise_if_not_found=False)
    if not user:
        _logger.warning('Некому показывать переписки — раздел не наполняю')
        return 0
    me = user.partner_id

    Channel = env['discuss.channel'].sudo()
    if Channel.search_count([('coop_kind', '!=', False)]):
        _logger.info('Переписки уже загружены')
        return 0

    Partner = env['res.partner'].sudo()
    people = Partner.search(
        [('coop_is_participant', '=', True), ('is_company', '=', False),
         ('id', '!=', me.id)], order='id')
    if not people:
        _logger.warning('Нет участников — переписки не наполняю')
        return 0

    rnd = random.Random(20260903)
    now = fields.Datetime.now()
    made = {'channels': 0, 'messages': 0}

    def talk(channel, kind, others, count, last_dt):
        """Разговор в обратном порядке: от последней реплики вглубь."""
        when = last_dt
        lines = []
        for _step in range(count):
            author = me if rnd.random() < 0.45 else rnd.choice(others)
            lines.append((author, rnd.choice(TALK[kind]), when))
            when -= timedelta(hours=rnd.randint(1, 40))
        for author, body, moment in reversed(lines):
            _post(channel, author, body, moment)
        made['messages'] += len(lines)

    def spread():
        """Когда в переписке писали в последний раз.

        Разброс намеренно неравномерный: большинство разговоров идёт на
        этой неделе, но каждый пятый заглох месяцы назад — по таким и
        видно, что показывает колонка времени и как читается список,
        когда свежее и старое перемешано.
        """
        if rnd.random() < 0.2:
            return now - timedelta(days=rnd.randint(40, 400))
        return now - timedelta(hours=rnd.randint(1, 240))

    # ── Личные беседы ─────────────────────────────────────────────────
    for person in people[:45]:
        last = spread()
        channel = _channel(
            env, person.name, 'person', person, me, user,
            subtitle=person.city or 'Участник платформы')
        talk(channel, 'person', person, rnd.randint(3, 9), last)
        made['channels'] += 1

    # ── Организации ───────────────────────────────────────────────────
    orgs = Partner.search(
        [('is_company', '=', True), ('coop_is_participant', '=', True)],
        order='id', limit=40)
    for index, org in enumerate(orgs):
        members = people[index * 3:index * 3 + 3] or people[:3]
        last = spread()
        subtitle = '%s · %s пайщиков' % (
            org.city or 'Платформа', rnd.randint(12, 340))
        channel = _channel(
            env, org.name, 'org', members, me, user, subtitle=subtitle,
            res_model='res.partner', res_id=org.id,
            pinned=index < 2)
        talk(channel, 'org', members, rnd.randint(4, 12), last)
        made['channels'] += 1

    # ── Сделки ────────────────────────────────────────────────────────
    deals = env['coop.deal'].sudo().search([], order='id desc', limit=30)
    states = dict(env['coop.deal']._fields['state'].selection)
    for deal in deals:
        other = deal.party_b_id if deal.party_a_id == me else deal.party_a_id
        if not other or other == me:
            other = rnd.choice(people)
        last = spread()
        channel = _channel(
            env, deal.display_name, 'deal', other, me, user,
            subtitle=states.get(deal.state, 'Сделка'),
            res_model='coop.deal', res_id=deal.id)
        talk(channel, 'deal', other, rnd.randint(3, 10), last)
        made['channels'] += 1

    # ── Проекты ───────────────────────────────────────────────────────
    projects = env['coop.project'].sudo().search([], order='id', limit=30)
    for index, project in enumerate(projects):
        members = people[index * 2:index * 2 + 4] or people[:4]
        last = spread()
        channel = _channel(
            env, project.name, 'project', members, me, user,
            subtitle=project.city or 'Проект платформы',
            res_model='coop.project', res_id=project.id)
        talk(channel, 'project', members, rnd.randint(4, 14), last)
        made['channels'] += 1

    # ── Сообщества ────────────────────────────────────────────────────
    communities = env['coop.community'].sudo().search([], order='id', limit=25)
    for index, community in enumerate(communities):
        members = people[index * 4:index * 4 + 5] or people[:5]
        last = spread()
        channel = _channel(
            env, community.name, 'community', members, me, user,
            subtitle='%s участников' % rnd.randint(8, 900),
            res_model='coop.community', res_id=community.id)
        talk(channel, 'community', members, rnd.randint(5, 16), last)
        made['channels'] += 1

    # ── Служебные ─────────────────────────────────────────────────────
    robot = env.ref('base.partner_root', raise_if_not_found=False) or people[0]
    for name, subtitle in SERVICE_CHANNELS:
        when = spread()
        channel = _channel(env, name, 'service', robot, me, user, subtitle=subtitle)
        for _step in range(rnd.randint(2, 6)):
            _post(channel, robot, rnd.choice(TALK['service']), when)
            when -= timedelta(days=rnd.randint(1, 20))
            made['messages'] += 1
        made['channels'] += 1

    # ── Пустая переписка ──────────────────────────────────────────────
    #
    # Заведена и брошена: так проверяется, что показывает лента без
    # сообщений и что пишется в колонке времени, когда писать нечего.
    _channel(env, rnd.choice(people).name, 'person', rnd.choice(people), me,
             user, subtitle='Переписка ещё не начата')
    made['channels'] += 1

    _mark_unread(env, me)

    _logger.info('Переписки: %(channels)s, сообщений: %(messages)s', made)
    return made['channels']


def _mark_unread(env, me):
    """Прочитанное, непрочитанное и свежесть разговора.

    Движок считает непрочитанные не счётчиком, а границей: непрочитано
    всё, что новее отметки в составе канала. Поэтому отметка и двигается —
    записанный счётчик движок перепишет при первом же открытии.

    Заодно каналу проставляется время последнего интереса. По умолчанию
    это момент создания, то есть у всех ста семидесяти переписок — одна и
    та же секунда загрузки: список выстроился бы по номерам, а колонка
    времени показывала бы «сегодня» везде.
    """
    env.cr.execute("""
        WITH last AS (
            SELECT res_id AS channel_id,
                   max(id) AS last_id,
                   max(date) AS last_dt
              FROM mail_message
             WHERE model = 'discuss.channel'
             GROUP BY res_id
        )
        UPDATE discuss_channel c
           SET last_interest_dt = last.last_dt
          FROM last
         WHERE last.channel_id = c.id
           AND c.coop_kind IS NOT NULL
    """)
    # Каждая пятая переписка остаётся непрочитанной: без них не видно ни
    # жирного начертания в списке, ни счётчика, ни фильтра «Непрочитанные».
    env.cr.execute("""
        WITH last AS (
            SELECT res_id AS channel_id, max(id) AS last_id
              FROM mail_message
             WHERE model = 'discuss.channel'
             GROUP BY res_id
        )
        UPDATE discuss_channel_member m
           SET new_message_separator = CASE WHEN mod(c.id, 5) = 0
                   THEN greatest(last.last_id - 2, 1)
                   ELSE last.last_id + 1 END,
               seen_message_id = CASE WHEN mod(c.id, 5) = 0
                   THEN NULL ELSE last.last_id END,
               last_interest_dt = c.last_interest_dt
          FROM discuss_channel c
          JOIN last ON last.channel_id = c.id
         WHERE m.channel_id = c.id
           AND c.coop_kind IS NOT NULL
    """)
