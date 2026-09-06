# -*- coding: utf-8 -*-
"""Витрина уступок: требования с отсрочкой и предложения по ним.

Уступают не абстрактный долг, а требование по конкретной сделке, где
работа уже принята, а деньги ещё не пришли. В генераторе сделок
завершённая сделка означала «оплачено полностью», и требований для
витрины из неё не возникало вовсе. В жизни так не бывает: акт подписан
сегодня, оплата через месяц — это и есть самый обычный случай, ради
которого уступка существует.

Поэтому загрузчик сначала возвращает части завершённых сделок отсрочку:
последний платёж становится ожидаемым, срок — в будущем. Заодно
оживают взаиморасчёты: до этого у всех завершённых сделок долгов не
оставалось ни у кого.
"""
import logging
import random

from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

# Сколько требований должно оказаться на витрине. Каталог, на котором не
# видно ни поиска, ни фильтров, ни постраничной навигации, каталогом не
# считается: правило платформы — сто-двести примеров в каждом разделе.
TARGET_DEFERRED = 170
TARGET_CESSIONS = 140

# Состояния предложений в тех долях, в каких они встречаются в жизни:
# большая часть висит и ждёт, по части идут переговоры, меньшая доля
# доведена до конца, немного снято. Черновики есть у всех, но их видит
# только автор — на витрину они не попадают.
STATES = (
    ['published'] * 58
    + ['negotiating'] * 20
    + ['done'] * 12
    + ['cancelled'] * 7
    + ['draft'] * 3
)

NOTES = [
    'Готов уступить с оплатой в течение трёх дней после подписания.',
    'Возможна оплата двумя частями, вторая — после уведомления должника.',
    'Должник платит аккуратно, просрочек по прошлым сделкам не было.',
    'Нужны оборотные средства на закупку сырья, поэтому и уступаю.',
    'Уступлю дешевле, если приобретатель берёт сразу два требования.',
    '',
    '',
    '',
]

RESPONSE_MESSAGES = [
    'Готов взять по вашей цене, если оформим на этой неделе.',
    'Возьму, но с дисконтом чуть больше: срок далёкий.',
    'Интересно. Уточните, чем подтверждено требование.',
    'Беру целиком, оплата в день подписания договора.',
    'Возьму половину, если допускаете частичную уступку.',
]


def load_cessions(env, target_deferred=TARGET_DEFERRED, target=TARGET_CESSIONS):
    Deal = env['coop.deal'].sudo()
    Payment = env['coop.deal.payment'].sudo()
    Cession = env['coop.cession'].sudo()
    Response = env['coop.cession.response'].sudo()

    rnd = random.Random(20260906)
    today = fields.Date.context_today(Deal)

    deferred = _make_deferred_payments(Deal, Payment, rnd, today, target_deferred)
    if not deferred:
        _logger.warning('Нет требований с отсрочкой — витрину уступок не наполняю')
        return

    partners = env['res.partner'].sudo().search([
        ('coop_is_participant', '=', True)], order='id')

    created = skipped = 0
    for index, deal in enumerate(deferred[:target]):
        key = 'cessions#%s' % deal.id
        if Cession.search_count([('import_key', '=', key)]):
            skipped += 1
            continue

        payment = deal.payment_ids.filtered(lambda p: p.state != 'paid')[:1]
        if not payment or not payment.payee_id or not payment.payer_id:
            continue

        amount = deal.amount_due
        # Дисконт от 2 до 18 процентов: ближний срок стоит дешевле
        # ожидания, дальний — дороже. Это не формула платформы, а разброс
        # для демонстрации; цену на витрине называет участник.
        days_left = (payment.due_on - today).days if payment.due_on else 30
        base = 2 + min(days_left, 120) / 10.0
        percent = round(rnd.uniform(base * 0.6, base * 1.4), 1)
        price = round(amount * (100 - percent) / 100.0, 2)

        state = STATES[index % len(STATES)]
        values = {
            'deal_id': deal.id,
            'creditor_id': payment.payee_id.id,
            'debtor_id': payment.payer_id.id,
            'amount': amount,
            'price': price,
            'due_date': payment.due_on,
            'state': state,
            'note': NOTES[index % len(NOTES)],
            'import_key': key,
        }
        if state != 'draft':
            values['published_on'] = fields.Datetime.now() - timedelta(
                days=rnd.randint(0, 45), hours=rnd.randint(0, 23))
        cession = Cession.create(values)

        if state in ('negotiating', 'done'):
            _make_responses(Response, cession, partners, rnd, state)
        if state == 'done':
            accepted = cession.response_ids.filtered(lambda r: r.state == 'accepted')
            cession.write({
                'assignee_id': accepted[:1].partner_id.id,
                'ceded_on': today - timedelta(days=rnd.randint(1, 30)),
                'debtor_notified_on': today - timedelta(days=rnd.randint(1, 30)),
            })
        created += 1

    # Часть сделок с запретом уступки: правило существует, и на витрине
    # должно быть видно, что оно работает, а не написано мелким шрифтом.
    _forbid_some(Deal, deferred, rnd)

    _logger.info('Витрина уступок: создано %s, пропущено %s', created, skipped)


def _make_deferred_payments(Deal, Payment, rnd, today, target):
    """Собрать пул требований, годных к уступке, и довести его до нужного.

    Годное требование — это принятая работа (акт подтверждён обеими
    сторонами), непогашенный остаток и платёж, из которого видно срок и
    кто кому платит. Стороны платежа важнее сторон сделки: «первая
    сторона» — это порядок полей, а не тот, кому должны.

    Пул добирается в три захода, от менее вмешательства к большему:

    1. Сделки, где всё уже есть, — их не трогаем вовсе.
    2. Сделки с остатком, но без графика платежей: график заводим. Стороны
       платежа Odoo подставит сама из способа сделки.
    3. Полностью оплаченные: последнему платежу возвращаем отсрочку. Это и
       есть обычная жизнь — акт подписан, деньги через месяц, — которой в
       генераторе сделок не было вовсе: там завершённая сделка означала
       «оплачено сразу и целиком».
    """
    def usable(deal):
        return bool(deal.payment_ids.filtered(
            lambda p: p.state != 'paid' and p.payee_id and p.payer_id))

    confirmed = Deal.search([
        ('act_confirmed_a', '=', True),
        ('act_confirmed_b', '=', True),
        ('state', 'not in', ('cancelled', 'disputed')),
    ], order='id')

    ready = confirmed.filtered(lambda d: d.amount_due > 0 and usable(d))

    # Заход второй: остаток есть, графика нет.
    for deal in confirmed.filtered(lambda d: d.amount_due > 0 and not d.payment_ids):
        if len(ready) >= target:
            break
        Payment.create({
            'deal_id': deal.id,
            'name': 'Оплата по договору с отсрочкой',
            'due_on': today + timedelta(days=rnd.randint(7, 120)),
            'amount': deal.amount_due,
            'state': 'planned',
        })
        if usable(deal):
            ready |= deal

    # Заход третий: оплачено целиком — возвращаем отсрочку.
    for deal in confirmed.filtered(lambda d: d.amount_due <= 0):
        if len(ready) >= target:
            break
        payment = deal.payment_ids.sorted('due_on')[-1:]
        if not payment:
            continue
        payment.write({
            'state': 'planned',
            'paid_on': False,
            'due_on': today + timedelta(days=rnd.randint(7, 120)),
        })
        if usable(deal):
            ready |= deal

    return ready


def _make_responses(Response, cession, partners, rnd, state):
    """Отклики: у части предложений один, у части несколько.

    Приобретателем может быть только участник платформы (п. 2 ст. 388 ГК
    это позволяет), поэтому откликаются участники, а не кто угодно.
    Кредитор и должник по этому же требованию в отклик не попадают.
    """
    pool = partners.filtered(
        lambda p: p not in (cession.creditor_id | cession.debtor_id))
    if not pool:
        return
    count = rnd.choice([1, 1, 2, 3])
    chosen = rnd.sample(list(pool), min(count, len(pool)))
    for position, partner in enumerate(chosen):
        Response.create({
            'cession_id': cession.id,
            'partner_id': partner.id,
            'message': RESPONSE_MESSAGES[
                (cession.id + position) % len(RESPONSE_MESSAGES)],
            # У доведённой до конца уступки один отклик принят, остальные
            # отклонены: требование одно, приобретатель у него один.
            'state': ('accepted' if (state == 'done' and position == 0)
                      else 'declined' if state == 'done' else 'new'),
        })


def _forbid_some(Deal, deferred, rnd):
    """Часть требований — необоротоспособные.

    Не для красоты: пока в каталоге нет ни одной такой сделки, правило
    «связанные с личностью кредитора не уступаются» проверить нельзя ни
    глазами, ни формой.
    """
    reasons = [
        'Требование связано с личностью кредитора (ст. 383 ГК)',
        'Уступка запрещена пунктом 8.4 договора',
        'Уступка допускается только с письменного согласия должника',
    ]
    # Двенадцать на весь стенд, а не двенадцать за прогон: загрузчик
    # выполняется при каждом обновлении модуля, и без этой проверки
    # необоротоспособных требований становилось бы всё больше с каждым
    # разом, пока витрина не опустела бы вовсе.
    already = Deal.search_count([('cession_forbidden', '=', True)])
    if already >= 12:
        return
    for position, deal in enumerate(deferred[-(12 - already):]):
        if deal.cession_forbidden:
            continue
        deal.write({
            'cession_forbidden': True,
            'cession_forbidden_reason': reasons[position % len(reasons)],
        })
