# -*- coding: utf-8 -*-
"""Добор примеров: по 25 на каждый случай.

Требование владельца: у каждого сценария должно быть не меньше 25
примеров. Причина простая и проверяемая: на трёх записях не видно ни
сортировки, ни фильтра, ни поведения экрана под нагрузкой, а состояние,
которого в данных нет вовсе, нельзя ни показать, ни проверить. Отклонённый
банком вывод, отклонённая сетью транзакция, круг взаимозачёта, который
никто не подписал, — всё это экраны, которые иначе никто не увидит до
боевой эксплуатации.

Загрузчик добирает, а не пересоздаёт: считает, сколько случаев уже есть,
и дописывает недостающие. Повторный прогон ничего не удваивает.
"""
import logging
import random

from odoo import fields

_logger = logging.getLogger(__name__)

TARGET = 25

# Сетевые операции: что бывает в блокчейн-кошельке.
TX_ASSETS = [
    ('btc', 'BTC', 0.004, 0.09, 7_270_000),
    ('eth', 'ETH', 0.05, 2.4, 221_000),
    ('eth', 'USDT', 50, 1200, 90),
    ('ton', 'TON', 20, 600, 330),
    ('sol', 'SOL', 1.0, 20, 9_000),
    ('koop', 'КООП', 100, 5000, 10),
]


def load_examples(env):
    made = {}
    made.update(_fiat_cases(env))
    made.update(_crypto_cases(env))
    made.update(_credit_cases(env))
    made.update(_clearing_cases(env))
    made.update(_share_cases(env))
    made.update(_deal_cases(env))
    made.update(_payment_cases(env))
    made.update(_review_cases(env))
    made.update(_token_cases(env))
    made.update(_verification_cases(env))
    made.update(_application_cases(env))
    made.update(_friendship_cases(env))
    made.update(_contribution_cases(env))
    made.update(_project_state_cases(env))
    made.update(_outcome_cases(env))
    _logger.info('Добор примеров по случаям: %s', made)
    return True


def _need(env, model, domain):
    """Сколько записей не хватает до двадцати пяти."""
    return max(0, TARGET - env[model].sudo().search_count(domain))


def _rnd():
    # Одно и то же зерно: разница между двумя прогонами должна означать
    # изменение данных, а не случайность.
    return random.Random(20260902)


# ── Кошелёк: фиат ───────────────────────────────────────────────────────

def _fiat_cases(env):
    Movement = env['coop.wallet.movement'].sudo()
    Wallet = env['coop.wallet'].sudo()
    wallets = Wallet.search([('method_ids', '!=', False)], limit=60)
    if not wallets:
        return {}
    rnd = _rnd()
    made = {}

    for kind, state, title in (
        ('correction', 'confirmed', 'Корректировка по акту сверки'),
        ('transfer', 'cancelled', 'Перевод участнику — отменён до отправки'),
    ):
        need = _need(env, 'coop.wallet.movement',
                     [('kind', '=', kind), ('state', '=', state)])
        for index in range(need):
            wallet = wallets[index % len(wallets)]
            Movement.create({
                'wallet_id': wallet.id,
                'date': '2026-%02d-%02d' % (1 + index % 9, 1 + index % 27),
                'name': title,
                'kind': kind,
                'amount': rnd.choice([-1, 1]) * rnd.randint(1500, 40000),
                'state': state,
            })
        made['фиат %s/%s' % (kind, state)] = need
    return made


# ── Кошелёк: сетевые операции ───────────────────────────────────────────

def _crypto_cases(env):
    Tx = env['coop.wallet.tx'].sudo()
    Wallet = env['coop.wallet'].sudo()
    Network = env['coop.wallet.network'].sudo()
    Partner = env['res.partner'].sudo()

    networks = {n.code: n for n in Network.with_context(active_test=False).search([])}
    wallets = Wallet.search([('asset_ids', '!=', False)], limit=60)
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=40)
    if not networks or not wallets:
        return {}

    rnd = _rnd()
    made = {}
    cases = [
        ('in', 'confirmed'), ('out', 'confirmed'), ('swap', 'confirmed'),
        ('fee', 'confirmed'), ('out', 'pending'), ('out', 'failed'),
    ]
    for kind, state in cases:
        need = _need(env, 'coop.wallet.tx',
                     [('kind', '=', kind), ('state', '=', state)])
        for index in range(need):
            wallet = wallets[index % len(wallets)]
            code, symbol, low, high, rate = TX_ASSETS[index % len(TX_ASSETS)]
            network = networks.get(code)
            if not network:
                continue
            quantity = round(rnd.uniform(low, high), 8)
            sign = 1 if kind == 'in' else -1
            values = {
                'wallet_id': wallet.id,
                'network_id': network.id,
                'date': '2026-%02d-%02d %02d:%02d:00' % (
                    1 + index % 9, 1 + index % 27, index % 24, (index * 7) % 60),
                'kind': kind,
                'symbol': symbol,
                'quantity': sign * quantity,
                'valuation': round(quantity * rate),
                'tx_hash': '%s_%040x' % (code, index * 104729 + 7),
                'state': state,
            }
            if kind == 'fee':
                values['quantity'] = -round(quantity / 400, 8)
                values['valuation'] = round(values['quantity'] * rate)
            if kind == 'swap':
                # Обмен — одна операция с двумя ногами. Вторая нога своим
                # полем: двумя строками потом не восстановить, что это был
                # один акт.
                other_code, other_symbol, o_low, o_high, _rate = TX_ASSETS[
                    (index + 3) % len(TX_ASSETS)]
                values['swap_symbol'] = other_symbol
                values['swap_quantity'] = round(rnd.uniform(o_low, o_high), 8)
                values['swap_network_id'] = networks.get(
                    other_code, network).id
            # У части операций вторая сторона — участник платформы: по
            # внешнему адресу человека не узнать, и это разные случаи.
            if kind in ('in', 'out'):
                if index % 3 == 0 and people:
                    values['peer_partner_id'] = people[index % len(people)].id
                else:
                    values['peer_address'] = '0x%040x' % (index * 65537 + 11)
            Tx.create(values)
        made['сеть %s/%s' % (kind, state)] = need
    return made


# ── Взаимный кредит ─────────────────────────────────────────────────────

def _credit_cases(env):
    Movement = env['coop.credit.movement'].sudo()
    Line = env['coop.credit.line'].sudo()
    lines = Line.search([], limit=60)
    if not lines:
        return {}
    rnd = _rnd()
    made = {}
    for state, title in (
        ('proposed', 'Помощь на площадке, смена'),
        ('declined', 'Не сошлись в оценке часов'),
        ('offset', 'Погашено взаимозачётом'),
    ):
        need = _need(env, 'coop.credit.movement', [('state', '=', state)])
        for index in range(need):
            line = lines[index % len(lines)]
            Movement.create({
                'line_id': line.id,
                'date': '2026-%02d-%02d' % (1 + index % 9, 1 + index % 27),
                'name': title,
                'amount': rnd.choice([-1, 1]) * rnd.randint(3, 30),
                'state': state,
                'proposed_by_id': line.partner_id.id,
                'confirmed_by_id': line.counterparty_id.id
                if state in ('offset',) else False,
            })
        made['кредит %s' % state] = need
    return made


def _clearing_cases(env):
    """Круги взаимозачёта во всех трёх состояниях.

    Подписанные и отменённые нужны не меньше предложенных: правило «не
    подписал один — раунд отменяется целиком» видно только на отменённом.
    """
    Clearing = env['coop.credit.clearing'].sudo()
    Signature = env['coop.credit.signature'].sudo()
    Line = env['coop.credit.line'].sudo()
    lines = Line.search([('balance', '!=', 0)], limit=200)
    if len(lines) < 9:
        return {}
    made = {}
    for state in ('proposed', 'signed', 'cancelled'):
        need = _need(env, 'coop.credit.clearing', [('state', '=', state)])
        for index in range(need):
            ring = lines[(index * 3) % (len(lines) - 3):][:3]
            if len(ring) < 3:
                continue
            participants = ring.mapped('partner_id') | ring.mapped('counterparty_id')
            clearing = Clearing.create({
                'name': 'Круг взаимных долгов № %s' % (index + 1),
                'amount': min(abs(line.balance) or 1 for line in ring),
                'participant_ids': [(6, 0, participants.ids)],
                'line_ids': [(6, 0, ring.ids)],
                'state': state,
            })
            for offset, partner in enumerate(participants):
                signed = state == 'signed' or (
                    state == 'proposed' and offset < len(participants) - 1)
                Signature.create({
                    'clearing_id': clearing.id,
                    'partner_id': partner.id,
                    'signed': signed,
                    'signed_on': fields.Date.context_today(clearing) if signed else False,
                })
        made['круг %s' % state] = need
    return made


# ── Паевой счёт ─────────────────────────────────────────────────────────

def _share_cases(env):
    Move = env['coop.share.move'].sudo()
    Account = env['coop.share.account'].sudo()
    accounts = Account.search([], limit=80)
    if not accounts:
        return {}
    rnd = _rnd()
    made = {}
    cases = [
        ('in_kind', 'confirmed', 'Взнос имуществом: трактор МТЗ-82',
         'Протокол общего собрания № 6', 'Отчёт об оценке № 114-О от 12.03.2025'),
        ('payout', 'confirmed', 'Выплата на руки по заявлению',
         'Заявление участника', False),
        ('return', 'confirmed', 'Возврат пая при выходе',
         'Протокол общего собрания № 9', False),
        ('payout', 'requested', 'Заявление на выплату', 'Заявление участника', False),
        ('payout', 'declined', 'Заявление отклонено: не истёк срок по уставу',
         'Решение правления № 3', False),
    ]
    for kind, state, title, basis, valuation in cases:
        need = _need(env, 'coop.share.move',
                     [('kind', '=', kind), ('state', '=', state)])
        for index in range(need):
            account = accounts[index % len(accounts)]
            amount = rnd.randint(20000, 180000)
            if kind in ('payout', 'return'):
                amount = -rnd.randint(3000, 60000)
            Move.create({
                'account_id': account.id,
                'date': '2026-%02d-%02d' % (1 + index % 9, 1 + index % 27),
                'name': title,
                'kind': kind,
                'basis': basis,
                'valuation_basis': valuation or False,
                'amount': amount,
                'state': state,
            })
        made['пай %s/%s' % (kind, state)] = need
    return made


# ── Сделки ──────────────────────────────────────────────────────────────

def _deal_cases(env):
    """Способы и состояния сделок, которых мало или нет вовсе.

    Дар и обмен важны отдельно: на них не бывает суммы, и именно они
    ломались бы, будь сделка сделана заказом Odoo.
    """
    Deal = env['coop.deal'].sudo()
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=60)
    companies = Partner.search([('coop_is_participant', '=', True),
                                ('is_company', '=', True)], limit=40)
    if len(people) < 2 or not companies:
        return {}
    rnd = _rnd()
    made = {}

    ways = [
        ('rent', 'resource', 'Аренда: погрузчик на неделю', 42000),
        ('purchase', 'resource', 'Покупка: комплект досок обрезных', 68000),
        ('gift', 'resource', 'Передача в дар: комплект инструмента', 0),
        ('exchange', 'resource', 'Обмен: мёд на пиломатериал', 0),
        ('job', 'work', 'Работа по вакансии: оператор сушилки', 45000),
        ('batch', 'resource', 'Продажа партией: картофель, 3 тонны', 96000),
        ('credit', 'credit', 'Взаимный кредит: отсрочка по поставке', 38000),
        ('share', 'project', 'Вклад в проект в обмен на долю', 150000),
    ]
    for way, subject, title, amount in ways:
        need = _need(env, 'coop.deal', [('way', '=', way)])
        for index in range(need):
            first = people[index % len(people)]
            second = companies[index % len(companies)]
            Deal.create({
                'name': title,
                'subject': subject,
                'way': way,
                'party_a_id': first.id,
                'party_b_id': second.id,
                'role_a': 'сторона',
                'role_b': 'вторая сторона',
                'city': rnd.choice(['Москва', 'Пермь', 'Казань', 'Омск', 'Тула']),
                'amount': amount,
                'signed_on': '2026-%02d-%02d' % (1 + index % 9, 1 + index % 27),
                'state': 'active',
                'import_key': 'examples.way.%s.%s' % (way, index),
            })
        made['сделка %s' % way] = need

    for state, title in (
        ('draft', 'Переговоры: аренда ангара под хранение'),
        ('acceptance', 'На приёмке: партия саженцев'),
        ('disputed', 'Спор: недопоставка тары'),
        ('cancelled', 'Отменена по соглашению сторон'),
    ):
        need = _need(env, 'coop.deal', [('state', '=', state)])
        for index in range(need):
            first = people[(index + 7) % len(people)]
            second = companies[(index + 3) % len(companies)]
            values = {
                'name': title,
                'subject': 'resource',
                'way': 'sale',
                'party_a_id': first.id,
                'party_b_id': second.id,
                'role_a': 'продавец',
                'role_b': 'покупатель',
                'amount': rnd.randint(8000, 220000),
                'signed_on': '2026-%02d-%02d' % (1 + index % 9, 1 + index % 27),
                'state': state,
                'import_key': 'examples.state.%s.%s' % (state, index),
            }
            if state == 'acceptance':
                # Одна сторона акт подтвердила, вторая ещё нет — ровно то,
                # что в макете названо «ждёт вас» и «ждёт контрагента».
                values['act_confirmed_a'] = index % 2 == 0
                values['act_confirmed_b'] = index % 2 == 1
            if state == 'disputed':
                values['dispute_opened_by_id'] = first.id
                values['dispute_reason'] = (
                    'Поставлено меньше согласованного, тара не соответствует '
                    'спецификации.')
            Deal.create(values)
        made['сделка %s' % state] = need
    return made


def _payment_cases(env):
    Payment = env['coop.deal.payment'].sudo()
    Deal = env['coop.deal'].sudo()
    deals = Deal.search([('amount', '>', 0)], limit=80)
    if not deals:
        return {}
    rnd = _rnd()
    made = {}
    for state, title in (
        ('overdue', 'Просроченный платёж'),
        ('cancelled', 'Платёж отменён при пересмотре условий'),
    ):
        need = _need(env, 'coop.deal.payment', [('state', '=', state)])
        for index in range(need):
            deal = deals[index % len(deals)]
            Payment.create({
                'deal_id': deal.id,
                'name': title,
                'due_on': '2026-%02d-%02d' % (1 + index % 8, 1 + index % 27),
                'amount': rnd.randint(4000, 60000),
                'state': state,
            })
        made['платёж %s' % state] = need
    return made


def _review_cases(env):
    """Оценки, которых нет: тройки, четвёрки и единицы.

    Без них доверие считается по двум крайностям, и середины — «сделали,
    но со скрипом» — в данных не существует, хотя в жизни она частая.
    """
    Review = env['coop.deal.review'].sudo()
    Deal = env['coop.deal'].sudo()
    made = {}
    texts = {
        '1': 'Договорённости не выполнены, пришлось искать замену.',
        '2': 'Сроки сорваны, качество ниже согласованного.',
        '3': 'Сделали, но со скрипом: сроки плыли, качество среднее.',
        '4': 'В целом хорошо, мелкие замечания по срокам.',
    }
    for rating, body in texts.items():
        need = _need(env, 'coop.deal.review', [('rating', '=', rating)])
        if not need:
            made['отзыв %s' % rating] = 0
            continue
        # Отзыв можно оставить только по завершённой сделке и только
        # один от каждой стороны. Сначала берём те, где своего отзыва ещё
        # нет; если их не хватает — заводим завершённые сделки под
        # оценку. Второе не подтасовка: сделка с одной средней оценкой —
        # обычное дело, а без неё середина шкалы в данных не существует.
        deals = Deal.search([('state', '=', 'done')], limit=600)
        created = 0
        for deal in deals:
            if created >= need:
                break
            authors = set(deal.review_ids.mapped('author_id').ids)
            for author, target in ((deal.party_a_id, deal.party_b_id),
                                   (deal.party_b_id, deal.party_a_id)):
                if created >= need or author.id in authors:
                    continue
                Review.create({
                    'deal_id': deal.id,
                    'author_id': author.id,
                    'target_id': target.id,
                    'rating': rating,
                    'body': body,
                })
                authors.add(author.id)
                created += 1
        created += _reviews_on_new_deals(env, rating, body, need - created)
        made['отзыв %s' % rating] = created
    return made


def _reviews_on_new_deals(env, rating, body, need):
    """Завести завершённые сделки под недостающие оценки."""
    if need <= 0:
        return 0
    Deal = env['coop.deal'].sudo()
    Review = env['coop.deal.review'].sudo()
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=80)
    companies = Partner.search([('coop_is_participant', '=', True),
                                ('is_company', '=', True)], limit=40)
    if len(people) < 2 or not companies:
        return 0
    created = 0
    for index in range(need):
        first = people[(index * 11 + int(rating)) % len(people)]
        second = companies[(index * 5 + int(rating)) % len(companies)]
        deal = Deal.create({
            'name': 'Поставка по договорённости',
            'subject': 'resource',
            'way': 'sale',
            'party_a_id': first.id,
            'party_b_id': second.id,
            'role_a': 'продавец',
            'role_b': 'покупатель',
            'amount': 15000 + index * 1300,
            'signed_on': '2026-0%s-%02d' % (1 + index % 8, 1 + index % 27),
            'state': 'done',
            'act_confirmed_a': True,
            'act_confirmed_b': True,
            'import_key': 'examples.review.%s.%s' % (rating, index),
        })
        Review.create({
            'deal_id': deal.id,
            'author_id': first.id,
            'target_id': second.id,
            'rating': rating,
            'body': body,
        })
        created += 1
    return created


# ── Токены ──────────────────────────────────────────────────────────────

def _token_cases(env):
    Token = env['coop.token.transaction'].sudo()
    Partner = env['res.partner'].sudo()
    partners = Partner.search([('coop_is_participant', '=', True)], limit=60)
    if not partners:
        return {}
    rnd = _rnd()
    made = {}
    for kind, sign, title in (
        ('grant', 1, 'Начисление за вклад в общее дело'),
        ('refund', 1, 'Возврат за неиспользованное продвижение'),
        ('correction', -1, 'Корректировка по обращению участника'),
        ('promotion', -1, 'Оплата продвижения объявления'),
    ):
        need = _need(env, 'coop.token.transaction', [('kind', '=', kind)])
        for index in range(need):
            Token.create({
                'partner_id': partners[index % len(partners)].id,
                'amount': sign * rnd.randint(5, 240),
                'kind': kind,
                'description': title,
            })
        made['токены %s' % kind] = need
    return made


# ── Верификация ─────────────────────────────────────────────────────────

def _verification_cases(env):
    """Заявки на проверку в состояниях, которых не было.

    Ожидающая и отклонённая проверка — рабочие состояния: человек подал,
    правление ещё не сверило либо документ не подошёл. Экрана для них не
    было на чём проверить.
    """
    Verification = env['coop.verification'].sudo()
    Partner = env['res.partner'].sudo()
    made = {}
    cases = [
        ('identity', 'pending', 'inperson'),
        ('identity', 'rejected', 'inperson'),
        ('phone', 'pending', 'self'),
        ('email', 'pending', 'self'),
        ('registry', 'pending', 'registry'),
    ]
    for kind, state, method in cases:
        need = _need(env, 'coop.verification',
                     [('kind', '=', kind), ('state', '=', state)])
        if not need:
            made['проверка %s/%s' % (kind, state)] = 0
            continue
        is_company = kind == 'registry'
        pool = Partner.search([
            ('coop_is_participant', '=', True),
            ('is_company', '=', is_company),
        ], order='id desc', limit=300)
        created = 0
        for partner in pool:
            if created >= need:
                break
            if Verification.search_count([('partner_id', '=', partner.id),
                                          ('kind', '=', kind)]):
                continue
            Verification.create({
                'partner_id': partner.id,
                'kind': kind,
                'method': method,
                'state': state,
                'note': 'Документ не соответствует заявленному'
                if state == 'rejected' else False,
            })
            created += 1
        created += _newcomers_for_verification(
            env, kind, state, method, need - created)
        made['проверка %s/%s' % (kind, state)] = created
    return made


def _newcomers_for_verification(env, kind, state, method, need):
    """Завести новичков, ждущих проверки.

    Свободных участников без такой проверки может не остаться: почти все
    в демо-данных уже подтверждены. Но платформа всегда имеет поток
    новых регистраций, ждущих проверки, — и это не выдумка ради цифры, а
    состояние, которое на работающем узле есть всегда.

    Новички попадают и в каталог людей — неподтверждёнными, как и
    положено: ступень «не подтверждён» тоже надо на чём-то показывать.
    """
    if need <= 0:
        return 0
    if kind == 'registry':
        return _newcomer_orgs(env, state, method, need)
    Partner = env['res.partner'].sudo()
    Verification = env['coop.verification'].sudo()
    # Отчество подбирается по случаю, чтобы у разных состояний были
    # разные люди: иначе второй случай упрётся в тех же, у кого проверка
    # уже заведена.
    patronymic = {
        ('identity', 'pending'): 'Сергеевич',
        ('identity', 'rejected'): 'Викторович',
        ('phone', 'pending'): 'Данилович',
        ('email', 'pending'): 'Максимович',
    }.get((kind, state), 'Иванович')
    names = [
        'Астахов Роман', 'Белкина Ольга', 'Гущин Артём', 'Дорохова Вера',
        'Ерёмин Павел', 'Жукова Инна', 'Зимин Кирилл', 'Ильина Раиса',
        'Кабанов Тимур', 'Лапина Дарья', 'Мещеряков Игорь', 'Нечаева Юлия',
        'Осипов Глеб', 'Панина Алла', 'Рогов Матвей', 'Седова Ксения',
        'Тарасов Лев', 'Ушакова Нина', 'Фомин Аркадий', 'Хохлова Елена',
        'Цветков Борис', 'Чернова Анна', 'Шилов Егор', 'Щукина Софья',
        'Юрьев Данила', 'Яшина Полина',
    ]
    cities = ['Пермь', 'Омск', 'Тула', 'Казань', 'Ижевск', 'Курск', 'Псков']
    created = 0
    for index in range(need):
        name = '%s %s' % (names[index % len(names)], patronymic)
        partner = Partner.search([('name', '=', name)], limit=1)
        if not partner:
            partner = Partner.create({
                'name': name,
                'is_company': False,
                'coop_is_participant': True,
                'city': cities[index % len(cities)],
            })
        if Verification.search_count([('partner_id', '=', partner.id),
                                      ('kind', '=', kind)]):
            continue
        Verification.create({
            'partner_id': partner.id,
            'kind': kind,
            'method': method,
            'state': state,
            'note': 'Документ не соответствует заявленному'
            if state == 'rejected' else False,
        })
        created += 1
    return created


def _newcomer_orgs(env, state, method, need):
    """Организации, только что подавшие сведения на сверку с реестром."""
    Partner = env['res.partner'].sudo()
    Verification = env['coop.verification'].sudo()
    forms = ['ООО', 'ПК', 'СПК', 'ТСЖ', 'АНО', 'Фонд', 'Артель']
    words = [
        'Заречье', 'Родник', 'Пойма', 'Веретено', 'Пасека', 'Оберег',
        'Слобода', 'Подворье', 'Заимка', 'Житница', 'Мельница', 'Криница',
        'Дубрава', 'Затон', 'Ольховка', 'Березань', 'Гончар', 'Скобянка',
        'Полесье', 'Взгорье', 'Тропа', 'Пристань', 'Кузня', 'Сенник',
        'Овражки', 'Луговина',
    ]
    created = 0
    for index in range(need):
        name = '%s «%s»' % (forms[index % len(forms)], words[index % len(words)])
        partner = Partner.search([('name', '=', name)], limit=1)
        if not partner:
            partner = Partner.create({
                'name': name,
                'is_company': True,
                'coop_is_participant': True,
            })
        if Verification.search_count([('partner_id', '=', partner.id),
                                      ('kind', '=', 'registry')]):
            continue
        Verification.create({
            'partner_id': partner.id,
            'kind': 'registry',
            'method': method,
            'state': state,
        })
        created += 1
    return created


# ── Отклики и заявки ────────────────────────────────────────────────────

def _application_cases(env):
    VacancyApp = env['coop.vacancy.application'].sudo()
    Vacancy = env['coop.vacancy'].sudo()
    BountyApp = env['coop.bounty.application'].sudo()
    Task = env['coop.bounty.task'].sudo()
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=200)
    made = {}

    vacancies = Vacancy.search([('state', '=', 'published')], limit=200)
    for state, letter in (
        ('applied', 'Работал на похожем оборудовании три сезона.'),
        ('invited', 'Приглашаем на разговор, свяжемся на неделе.'),
        ('declined', 'В этот раз выбрали другого кандидата.'),
    ):
        need = _need(env, 'coop.vacancy.application', [('state', '=', state)])
        created = 0
        for index, vacancy in enumerate(vacancies):
            if created >= need:
                break
            person = people[(index * 5 + hash(state) % 7) % len(people)]
            if VacancyApp.search_count([('vacancy_id', '=', vacancy.id),
                                        ('partner_id', '=', person.id)]):
                continue
            try:
                with env.cr.savepoint():
                    VacancyApp.create({
                        'vacancy_id': vacancy.id,
                        'partner_id': person.id,
                        'message': letter,
                        'state': state,
                    })
                created += 1
            except Exception:  # noqa: BLE001
                continue
        made['отклик %s' % state] = created

    tasks = Task.search([], limit=200)
    for state in ('applied', 'approved', 'rejected'):
        need = _need(env, 'coop.bounty.application', [('state', '=', state)])
        created = 0
        pairs = [(task, offset) for task in tasks for offset in range(10)]
        for index, (task, offset) in enumerate(pairs):
            if created >= need:
                break
            person = people[(index * 3 + offset * 11 + len(state)) % len(people)]
            if BountyApp.search_count([('task_id', '=', task.id),
                                       ('partner_id', '=', person.id)]):
                continue
            try:
                with env.cr.savepoint():
                    BountyApp.create({
                        'task_id': task.id,
                        'partner_id': person.id,
                        'state': state,
                    })
                created += 1
            except Exception:  # noqa: BLE001
                continue
        made['заявка %s' % state] = created
    return made


def _friendship_cases(env):
    Friendship = env['coop.friendship'].sudo()
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=200)
    if len(people) < 10:
        return {}
    made = {}
    # Отсчёт пар сквозной, а не с нуля на каждое состояние. С нуля каждое
    # состояние бралось за те же самые пары, и одна пара заводилась трижды
    # — на стенде так вышло 25 пар-дублей из 75 связей. Уникальности в
    # базе тогда не было (см. `models.Constraint`), и дубли просто копили
    # счётчик друзей: у человека с одним другом их выходило три.
    index = 0
    for state in ('pending', 'accepted', 'declined'):
        need = _need(env, 'coop.friendship', [('state', '=', state)])
        created = 0
        attempts = 0
        while created < need and attempts < len(people) * 3:
            first = people[index % len(people)]
            second = people[(index * 7 + 13) % len(people)]
            index += 1
            attempts += 1
            if first == second:
                continue
            try:
                with env.cr.savepoint():
                    Friendship.create({
                        'requester_id': first.id,
                        'addressee_id': second.id,
                        'state': state,
                    })
                created += 1
            except Exception:  # noqa: BLE001
                continue
        made['дружба %s' % state] = created
    return made


def _contribution_cases(env):
    Contribution = env['coop.project.contribution'].sudo()
    Project = env['coop.project'].sudo()
    Partner = env['res.partner'].sudo()
    projects = Project.search([('state', '=', 'gathering')], limit=80)
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=60)
    if not projects or not people:
        return {}
    rnd = _rnd()
    made = {}
    for state, title in (
        ('offered', 'Предложен: ждёт оценки инициатора'),
        ('declined', 'Отклонён: оценка вклада не согласована'),
        ('returned', 'Возвращён по выходу участника из проекта'),
    ):
        need = _need(env, 'coop.project.contribution', [('state', '=', state)])
        for index in range(need):
            project = projects[index % len(projects)]
            Contribution.create({
                'project_id': project.id,
                'partner_id': people[index % len(people)].id,
                'kind': rnd.choice(['money', 'labour', 'resource', 'material']),
                'name': title,
                'value': rnd.randint(15000, 300000),
                'state': state,
            })
        made['вклад %s' % state] = need
    return made


def _project_state_cases(env):
    """Проекты во всех состояниях пути.

    Запущенных и завершённых в макете почти нет: там готовность нигде не
    доходит до ста. А именно на них проверяется передача проекта в модуль
    управления и распределение долей по итогам — то, ради чего
    краудресурсинг и затевается.
    """
    Project = env['coop.project'].sudo()
    Contribution = env['coop.project.contribution'].sudo()
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=60)
    if not people:
        return {}
    made = {}
    for state in ('draft', 'running', 'done', 'cancelled'):
        need = _need(env, 'coop.project', [('state', '=', state)])
        created = 0
        # Проще довести до состояния уже собранные проекты, чем заводить
        # новые: у них есть вклады, а без вкладов «запущенный» проект —
        # запись ни о чём.
        pool = Project.search([('state', '=', 'gathering')], order='readiness desc')
        for project in pool:
            if created >= need:
                break
            if state in ('running', 'done') and project.readiness < 100:
                # Дособрать вкладом: запускать недособранный проект
                # нельзя, и обходить собственное правило в данных тоже.
                missing = project.required_total - project.contribution_total
                if missing > 0:
                    Contribution.create({
                        'project_id': project.id,
                        'partner_id': people[created % len(people)].id,
                        'kind': 'money',
                        'name': 'Замыкающий взнос',
                        'value': missing,
                        'state': 'accepted',
                    })
            project.state = state
            # Проект в модуле управления здесь не заводится. Он создаётся
            # кнопкой запуска, и при загрузке модулей это не проходит:
            # у штатного проекта есть обязательное поле, которое
            # добавляет модуль учёта времени, и его значение при загрузке
            # до записи не доезжает. Ради демонстрационных данных
            # обходить чужую механику незачем — состояния «запущен» и
            # «завершён» показывают то, ради чего они нужны, и без этой
            # ссылки.
            created += 1
        made['проект %s' % state] = created
    return made


def _outcome_cases(env):
    """Итоги сделок: недовольные обе стороны и ждущие второго отзыва.

    Итог считается из отзывов, поэтому его нельзя проставить — только
    сложить из оценок. «Ждём отзывов» получается там, где написал один;
    «обе недовольны» — где оба поставили низкую оценку. Оба состояния в
    жизни частые, и без них экран сделок показывает только успех.
    """
    Deal = env['coop.deal'].sudo()
    Review = env['coop.deal.review'].sudo()
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=80)
    companies = Partner.search([('coop_is_participant', '=', True),
                                ('is_company', '=', True)], limit=40)
    if len(people) < 2 or not companies:
        return {}
    made = {}
    for outcome, both, rating, body in (
        ('negative', True, '2', 'Договорённости не выдержаны обеими сторонами.'),
        ('pending', False, '4', 'Свою оценку поставил, жду ответной.'),
    ):
        need = _need(env, 'coop.deal', [('outcome', '=', outcome)])
        for index in range(need):
            first = people[(index * 13 + len(outcome)) % len(people)]
            second = companies[(index * 7 + len(outcome)) % len(companies)]
            deal = Deal.create({
                'name': 'Поставка по договорённости',
                'subject': 'resource',
                'way': 'sale',
                'party_a_id': first.id,
                'party_b_id': second.id,
                'role_a': 'продавец',
                'role_b': 'покупатель',
                'amount': 12000 + index * 900,
                'signed_on': '2026-%02d-%02d' % (1 + index % 8, 1 + index % 27),
                'state': 'done',
                'act_confirmed_a': True,
                'act_confirmed_b': True,
                'import_key': 'examples.outcome.%s.%s' % (outcome, index),
            })
            Review.create({
                'deal_id': deal.id, 'author_id': first.id,
                'target_id': second.id, 'rating': rating, 'body': body,
            })
            if both:
                Review.create({
                    'deal_id': deal.id, 'author_id': second.id,
                    'target_id': first.id, 'rating': rating, 'body': body,
                })
        made['итог %s' % outcome] = need
    return made
