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

# Тестовые учётки владельца — и под прежними именами, и под новыми
# (`load_people.TEST_RENAMES`).
TEST_NAMES = ('Danil', 'Proverka Vyhoda',
              'Игнатьев Денис Олегович', 'Прохорова Вера Андреевна')


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


def load_wall_likes(env):
    """Лайки и дизлайки под записями стен (решение 404, вид ряда — со слов
    владельца: «цифрами количество лайков … количество дизлайков»).

    Лайк и дизлайк — реакции движка 👍 и 👎. Раскладка неровная: у
    половины записей лайков нет вовсе; у остальных — от одного до двух
    десятков, у витринных записей побольше; дизлайки редки — у одной
    записи из десяти, по одному-три. Один человек не ставит и то и другое
    сразу. Ставят участники, не автор записи.

    Прогон один: если под записями стен уже есть 👍 или 👎, ничего не
    делается (урок комментариев — жребий по «ещё пустым» удваивал
    наполнение).
    """
    Reaction = env['mail.message.reaction'].sudo()
    Message = env['mail.message'].sudo()
    Partner = env['res.partner'].sudo()
    if Reaction.search_count([
            ('content', 'in', ('👍', '👎')),
            ('message_id.model', '=', 'res.partner')], limit=1):
        _logger.info("Лайки на стенах: уже наполнено, пропускаю")
        return 0
    rnd = random.Random(20260924 + 405)
    posts = Message.search([
        ('model', '=', 'res.partner'), ('message_type', '=', 'comment'),
        ('subtype_id.internal', '=', False),
    ])
    people = list(Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('name', 'not in', TEST_NAMES),
    ]))
    showcase = env['res.users'].sudo().search(
        [('login', '=', 'dashkevich')], limit=1).partner_id
    if not posts or len(people) < 30:
        return 0
    rows = []
    for post in posts:
        mine = showcase and post.res_id == showcase.id
        likes = rnd.randint(4, 28) if mine else (
            0 if rnd.random() < 0.5 else rnd.randint(1, 20))
        dislikes = rnd.randint(1, 3) if rnd.random() < 0.1 else 0
        if not likes and not dislikes:
            continue
        crowd = [p for p in rnd.sample(people, min(len(people), likes + dislikes + 1))
                 if p != post.author_id][:likes + dislikes]
        for n, person in enumerate(crowd):
            rows.append({
                'message_id': post.id,
                'content': '👍' if n < likes else '👎',
                'partner_id': person.id,
            })
    if rows:
        Reaction.create(rows)
    _logger.info("Лайки на стенах: поставлено %s", len(rows))
    return len(rows)


REPOST_WORDS = [
    '', '', '',
    'Полезно, сохраняю себе.',
    'Кому нужно — обращайтесь, рекомендую.',
    'Делюсь: вдруг кому-то из знакомых пригодится.',
    'Хороший пример, как надо.',
    'Поддержим!',
    'Коллеги, обратите внимание.',
    'Тоже ищем такое — может, объединимся?',
]


def load_wall_reposts(env):
    """Репосты записей со стен (решение 404).

    Около полутора сотен: участник приносит к себе на стену чужую запись,
    иногда со своими словами, чаще без них. Одну запись к себе дважды не
    приносят; своё не репостят. Время — после исходной записи, не позже
    сегодняшнего дня. Записи заводятся прямо сообщениями, минуя рассылку
    подписчикам, как и сами записи стен.

    Прогон один: если репосты уже есть, ничего не делается.
    """
    Message = env['mail.message'].sudo()
    Partner = env['res.partner'].sudo()
    if Message.search_count([('coop_repost_of_id', '!=', False)], limit=1):
        _logger.info("Репосты на стенах: уже наполнено, пропускаю")
        return 0
    rnd = random.Random(20260924 + 406)
    now = datetime.now()
    comment = env.ref('mail.mt_comment')
    posts = list(Message.search([
        ('model', '=', 'res.partner'), ('message_type', '=', 'comment'),
        ('subtype_id.internal', '=', False),
    ]))
    people = list(Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('name', 'not in', TEST_NAMES),
    ]))
    if len(posts) < 50 or len(people) < 30:
        return 0
    rows, seen = [], set()
    for post in rnd.sample(posts, min(len(posts), 110)):
        for _n in range(rnd.choice((1, 1, 1, 2, 3))):
            person = rnd.choice(people)
            if person == post.author_id or (post.id, person.id) in seen:
                continue
            seen.add((post.id, person.id))
            start = post.date or now
            window = min(now - start, timedelta(days=14))
            if window <= timedelta(minutes=10):
                continue
            words = rnd.choice(REPOST_WORDS)
            rows.append({
                'model': 'res.partner',
                'res_id': person.id,
                'message_type': 'comment',
                'subtype_id': comment.id,
                'author_id': person.id,
                'body': '<p>%s</p>' % words if words else '',
                'date': start + window * rnd.uniform(0.05, 1.0),
                'coop_repost_of_id': post.id,
            })
    rows.sort(key=lambda row: row['date'])
    if rows:
        Message.create(rows)
    _logger.info("Репосты на стенах: заведено %s", len(rows))
    return len(rows)


def load_wall_thanks(env, login='dashkevich'):
    """Благодарности авторам записей (решение 406) — около ста шестидесяти.

    Приём включён примерно у трети людей и у главного участника витрины;
    телефоны СБП — заведомо учебные, из диапазона +7 900 000-xx-xx. Токенами —
    только тем, у кого в кошельке есть адрес в сети; сеть и токен — разные. Состояния — все пять,
    неровно: больше подтверждённых, есть заявленные (их автор может
    отметить сам), не пришедшие, возвращённые и спорные. Время — между
    записью и сегодняшним днём.

    Прогон один: если благодарности уже есть, ничего не делается.
    """
    Thanks = env['coop.wall.thanks'].sudo()
    if Thanks.search_count([], limit=1):
        _logger.info("Благодарности: уже наполнено, пропускаю")
        return 0
    Message = env['mail.message'].sudo()
    Partner = env['res.partner'].sudo()
    rnd = random.Random(20260924 + 407)
    now = datetime.now()
    people = list(Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('name', 'not in', TEST_NAMES),
    ]))
    if len(people) < 30:
        return 0
    showcase = env['res.users'].sudo().search(
        [('login', '=', login)], limit=1).partner_id
    takers = [p for p in people if rnd.random() < 0.35]
    if showcase and showcase not in takers:
        takers.append(showcase)
    for n, person in enumerate(takers):
        person.write({
            'coop_thanks_on': True,
            'coop_thanks_sbp': '+7 900 000-%02d-%02d' % (n // 100 % 100, n % 100),
        })
    nets = {p.id: Thanks._coop_networks(p) for p in takers}

    posts = list(Message.search([
        ('model', '=', 'res.partner'), ('message_type', '=', 'comment'),
        ('subtype_id.internal', '=', False),
        ('author_id', 'in', [p.id for p in takers]),
    ]))
    if not posts:
        return 0
    mine = [p for p in posts if showcase and p.author_id == showcase]
    others = [p for p in posts if p not in mine]
    chosen = mine + rnd.sample(others, min(len(others), 95))
    states = (['confirmed'] * 11 + ['declared'] * 4 + ['unconfirmed'] * 2
              + ['returned'] + ['disputed'] * 2)
    rows = []
    for post in chosen:
        for _n in range(rnd.choice((1, 1, 1, 2, 2, 3)) + (1 if post in mine else 0)):
            sender = rnd.choice(people)
            if sender == post.author_id:
                continue
            gift = _token_gift(rnd, nets.get(post.author_id.id)) if rnd.random() < 0.3 else None
            channel = 'token' if gift else 'sbp'
            amount = gift['amount'] if gift else rnd.choice(
                (50, 100, 100, 150, 200, 300, 500, 500, 700, 1000, 1500, 2000, 3000))
            start = post.date or now
            window = min(now - start, timedelta(days=12))
            if window <= timedelta(minutes=10):
                continue
            rows.append({
                'post_id': post.id,
                'sender_id': sender.id,
                'recipient_id': post.author_id.id,
                'channel': channel,
                'network_id': gift['network_id'] if gift else False,
                'token': gift['token'] if gift else False,
                'amount': amount,
                'state': rnd.choice(states),
                'date': start + window * rnd.uniform(0.05, 1.0),
            })
    if rows:
        Thanks.create(rows)
    _logger.info("Благодарности: приём у %s человек, заведено %s", len(takers), len(rows))
    return len(rows)


# Сколько обычно дарят в каждом токене — чтобы суммы выглядели как в жизни,
# а не «1 BTC за запись».
TOKEN_AMOUNTS = {
    'BTC': (0.0002, 0.0005, 0.001, 0.002),
    'ETH': (0.002, 0.005, 0.01, 0.02),
    'BNB': (0.01, 0.02, 0.05, 0.1),
    'TON': (0.5, 1, 2, 3, 5, 10),
    'SOL': (0.05, 0.1, 0.2, 0.5),
    'USDT': (1, 2, 5, 10, 20, 50),
    'USDC': (1, 2, 5, 10, 25),
}


def _token_gift(rnd, networks):
    if not networks:
        return None
    network = rnd.choice(networks)
    token = rnd.choice(network['tokens'])['symbol']
    return {
        'network_id': network['id'],
        'token': token,
        'amount': rnd.choice(TOKEN_AMOUNTS.get(token, (1, 2, 5))),
    }


def load_wall_thanks_tokens(env):
    """Подарки токенами во всех сетях (владелец 24 сентября 2026: вкладка
    «Токенами» с выбором блокчейна). Первое наполнение подарков вышло до
    вкладки, и токенами там был один TON; здесь — около пятидесяти
    подарков в BTC, ETH, USDT, USDC, BNB, SOL и TON.

    Прогон один: если подарок токенами не в сети TON уже есть, ничего не
    делается.
    """
    Thanks = env['coop.wall.thanks'].sudo()
    if Thanks.search_count([('channel', '=', 'token'),
                            ('network_id.code', '!=', 'ton')], limit=1):
        _logger.info("Подарки токенами: уже наполнено, пропускаю")
        return 0
    Message = env['mail.message'].sudo()
    Partner = env['res.partner'].sudo()
    rnd = random.Random(20260924 + 408)
    now = datetime.now()
    takers = Partner.search([('coop_thanks_on', '=', True)])
    nets = {p.id: Thanks._coop_networks(p) for p in takers}
    authors = [pid for pid, n in nets.items() if n]
    people = list(Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('name', 'not in', TEST_NAMES),
    ]))
    posts = list(Message.search([
        ('model', '=', 'res.partner'), ('message_type', '=', 'comment'),
        ('subtype_id.internal', '=', False), ('author_id', 'in', authors),
    ]))
    if not posts or len(people) < 30:
        return 0
    states = (['confirmed'] * 11 + ['declared'] * 4 + ['unconfirmed'] * 2
              + ['returned'] + ['disputed'] * 2)
    rows = []
    for post in rnd.sample(posts, min(len(posts), 50)):
        sender = rnd.choice(people)
        gift = _token_gift(rnd, nets[post.author_id.id])
        start = post.date or now
        window = min(now - start, timedelta(days=12))
        if sender == post.author_id or not gift or window <= timedelta(minutes=10):
            continue
        rows.append({
            'post_id': post.id,
            'sender_id': sender.id,
            'recipient_id': post.author_id.id,
            'channel': 'token',
            'network_id': gift['network_id'],
            'token': gift['token'],
            'amount': gift['amount'],
            'state': rnd.choice(states),
            'date': start + window * rnd.uniform(0.05, 1.0),
        })
    if rows:
        Thanks.create(rows)
    _logger.info("Подарки токенами: заведено %s", len(rows))
    return len(rows)


def load_wall_stars(env, login='dashkevich'):
    """Звёздочки «в избранное» под записями стен (решение 408; число у
    звёздочки — владелец 24 сентября 2026: «в ленте цифру забыл к иконке
    избранного»).

    Около трети записей сохранили от одного до восьми человек; у витринных
    записей — побольше. Главный участник сохранил около тридцати чужих
    записей — они же вкладка «Записи» на странице «Избранное».

    Прогон один: если звёздочки под записями стен уже есть, ничего не
    делается.
    """
    Message = env['mail.message'].sudo()
    Partner = env['res.partner'].sudo()
    posts = Message.search([
        ('model', '=', 'res.partner'), ('message_type', '=', 'comment'),
        ('subtype_id.internal', '=', False),
    ])
    if posts.filtered('starred_partner_ids')[:1]:
        _logger.info("Звёздочки на стенах: уже наполнено, пропускаю")
        return 0
    rnd = random.Random(20260924 + 409)
    people = list(Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('name', 'not in', TEST_NAMES),
    ]))
    showcase = env['res.users'].sudo().search(
        [('login', '=', login)], limit=1).partner_id
    if len(people) < 30:
        return 0
    others = [p for p in posts if not showcase or p.author_id != showcase]
    mine_saved = set(p.id for p in rnd.sample(others, min(len(others), 30)))
    total = 0
    for post in posts:
        own = showcase and post.author_id == showcase
        n = rnd.randint(2, 12) if own else (rnd.randint(1, 8) if rnd.random() < 0.33 else 0)
        fans = {p.id for p in rnd.sample(people, min(n, len(people))) if p != post.author_id}
        if showcase and post.id in mine_saved:
            fans.add(showcase.id)
        if fans:
            post.write({'starred_partner_ids': [(4, pid) for pid in fans]})
            total += len(fans)
    _logger.info("Звёздочки на стенах: поставлено %s", total)
    return total


# Коды банков в СБП — настоящие участники системы, чтобы ссылка выглядела
# так, как её выдаёт банк.
SBP_BANKS = ('100000000111', '100000000004', '100000000008', '100000000005',
             '100000000007', '100000000015', '100000000001')


def load_thanks_sbp_links(env, login='dashkevich'):
    """Ссылки СБП для QR-кода в окне «Поблагодарить».

    Владелец 24 сентября 2026: «у нас был выбор между СБП по QR-коду или
    токены». По номеру телефона QR-кода не бывает — нужна ссылка, какую
    выдаёт банк (`https://qr.nspk.ru/…`). Около двух третей принимающих
    подарки (и главный участник) получают ссылку, остальные остаются с
    телефоном — чтобы были видны оба случая. Ссылки учебные: номер
    перевода случайный, по нему банк ничего не откроет.

    Прогон один: если ссылки уже есть, ничего не делается.
    """
    Partner = env['res.partner'].sudo()
    if Partner.search_count([('coop_thanks_sbp', '=like', 'https://qr.nspk.ru/%')], limit=1):
        _logger.info("Ссылки СБП: уже наполнено, пропускаю")
        return 0
    rnd = random.Random(20260924 + 411)
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    showcase = env['res.users'].sudo().search([('login', '=', login)], limit=1).partner_id
    takers = Partner.search([('coop_thanks_on', '=', True)])
    done = 0
    for person in takers:
        if person != showcase and rnd.random() > 0.66:
            continue
        code = ''.join(rnd.choice(alphabet) for _n in range(32))
        crc = ''.join(rnd.choice('0123456789ABCDEF') for _n in range(4))
        person.coop_thanks_sbp = 'https://qr.nspk.ru/%s?type=01&bank=%s&crc=%s' % (
            code, rnd.choice(SBP_BANKS), crc)
        done += 1
    _logger.info("Ссылки СБП: заведено %s", done)
    return done


_B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
_B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'


def _tx_hash(code, seed):
    rnd = random.Random('tx:%s:%s' % (code, seed))
    hexs = ''.join(rnd.choice('0123456789abcdef') for _ in range(64))
    if code in ('eth', 'bnb'):
        return '0x' + hexs
    if code == 'ton':
        return ''.join(rnd.choice(_B64) for _ in range(43)) + '='
    if code == 'sol':
        return ''.join(rnd.choice(_B58) for _ in range(88))
    return hexs


def repair_thanks_hashes(env):
    """Подаркам токенами — хеш транзакции и время зачисления (для справки
    к 3-НДФЛ, решение 410, п. 1). Хеш — в формате своей сети, вымышленный.
    Повторный запуск ничего не меняет."""
    if 'coop.wall.thanks' not in env or 'tx_hash' not in env['coop.wall.thanks']._fields:
        return 0
    Thanks = env['coop.wall.thanks'].sudo()
    rnd = random.Random(20260925 + 406)
    fixed = 0
    for thanks in Thanks.search([('channel', '=', 'token'), ('tx_hash', '=', False)]):
        vals = {}
        # У части подарков хеш даритель не вписал — такое бывает.
        if rnd.random() < 0.85:
            vals['tx_hash'] = _tx_hash(thanks.network_id.code or 'btc', thanks.id)
        if thanks.state == 'confirmed' and not thanks.credited_on:
            vals['credited_on'] = thanks.date + timedelta(minutes=rnd.randint(1, 180))
        if vals:
            thanks.write(vals)
            fixed += 1
    if fixed:
        _logger.info('Подарки токенами: хеш и зачисление у %s', fixed)
    return fixed
