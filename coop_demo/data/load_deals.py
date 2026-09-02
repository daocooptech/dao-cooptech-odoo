# -*- coding: utf-8 -*-
"""Каталог сделок из макета — со спецификацией, платежами и отзывами.

Сто сделок из `deals.html`. Сделка — единственный раздел, где видно, как
платформа работает целиком: у неё есть предмет из каталога, стороны с их
ролями, деньги, приёмка и взаимные отзывы, от которых считается доверие.

Отзывы раскладываются по правилу платформы, а не выставляются: оба
показываются, только когда написаны оба. Поэтому у части завершённых
сделок отзыв один — эти сделки и должны выглядеть как ждущие второго.
"""
import io
import json
import logging
import os
import random
import re

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

SUBJECT = {
    'Ресурс': 'resource',
    'Услуга': 'service',
    'Работа': 'work',
    'Проект': 'project',
    'Взаимный кредит': 'credit',
}

WAY = {
    'Продажа': 'sale',
    'Покупка': 'purchase',
    'Продажа партией': 'batch',
    'Аренда': 'rent',
    'Обмен': 'exchange',
    'Услуга': 'service',
    'Работа по вакансии': 'job',
    'Доля в проекте': 'share',
    'Взаимный кредит': 'credit',
}

STATE = {
    'active': 'active',
    'await-mine': 'acceptance',
    'await-theirs': 'acceptance',
    'done': 'done',
}

MONTHS = {
    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
    'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11,
    'декабря': 12,
}

# Роль второй стороны по роли первой: у сделки две стороны, и назвать
# нужно обе — «продавец» без «покупателя» ничего не описывает.
COUNTER_ROLE = {
    'арендатор': 'арендодатель',
    'покупатель': 'продавец',
    'продавец': 'покупатель',
    'исполнитель': 'заказчик',
    'заёмщик': 'кредитор',
    'кредитор': 'заёмщик',
    'обменивающийся': 'обменивающийся',
    'участник': 'инициатор проекта',
}

REVIEW_GOOD = [
    'Всё по договорённости, сроки выдержаны.',
    'Работали второй раз, снова без нареканий.',
    'Технику передали в срок и в порядке.',
    'Спокойно, по-деловому, вопросов не осталось.',
]
REVIEW_BAD = [
    'Сроки сдвинулись дважды, предупредили в последний момент.',
    'Часть работ пришлось переделывать за свой счёт.',
    'На связь выходили неохотно, договорённости менялись.',
]


def load_deals(env, extra=45):
    with io.open(os.path.join(HERE, 'deals.json'), encoding='utf-8') as fh:
        rows = json.load(fh)

    Deal = env['coop.deal'].sudo()
    Line = env['coop.deal.line'].sudo()
    Payment = env['coop.deal.payment'].sudo()
    Review = env['coop.deal.review'].sudo()
    Partner = env['res.partner'].sudo()

    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)], order='id')
    companies = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)], order='id')
    if not people or not companies:
        _logger.warning('Нет участников — сделки не наполняю')
        return

    # Часть сделок — с участием администратора стенда: иначе он открывает
    # раздел и видит пустоту, потому что чужие сделки ему не показываются
    # правилом доступа, и это правильно.
    me = env.ref('base.user_admin').partner_id

    rnd = random.Random(20260902)
    created = skipped = 0

    for index, row in enumerate(rows + _extra_rows(rows, extra, rnd)):
        key = 'deals.json#%s' % index
        if Deal.search_count([('import_key', '=', key)]):
            skipped += 1
            continue

        counterparty = _find_party(Partner, row['party'], people, companies, index)
        mine = me if index % 3 == 0 else people[(index * 7) % len(people)]
        if mine == counterparty:
            mine = people[(index * 7 + 1) % len(people)]

        role_a = row['my_role'] or 'сторона'
        values = {
            'name': row['name'],
            'subject': SUBJECT.get(row['subject'], 'resource'),
            'way': WAY.get(row['way'], 'sale'),
            'party_a_id': mine.id,
            'party_b_id': counterparty.id,
            'role_a': role_a,
            'role_b': COUNTER_ROLE.get(role_a, 'вторая сторона'),
            'author_id': (mine if not mine.is_company else people[index % len(people)]).id,
            'city': row['city'],
            'amount': _amount(row['amount_text']),
            'signed_on': _date(row['date_text'], row['year']),
            'state': STATE.get(row['status'], 'active'),
            'import_key': key,
        }
        deal = Deal.create(values)
        created += 1

        _make_lines(Line, deal, rnd, index)
        if deal.amount:
            _make_payments(Payment, deal, rnd, index)
        if deal.state == 'done':
            deal.write({
                'act_confirmed_a': True,
                'act_confirmed_b': True,
                'act_confirmed_on': deal.signed_on,
                'closed_on': deal.signed_on,
            })
            _make_reviews(Review, deal, row, index)
        elif deal.state == 'acceptance':
            # Ждём подтверждения одной из сторон — ровно то, что в макете
            # называется «ждёт вас» и «ждёт контрагента».
            side = 'a' if row['status'] == 'await-theirs' else 'b'
            deal.write({'act_confirmed_%s' % side: True})

    _logger.info('Каталог сделок: создано %s, пропущено %s', created, skipped)


def _find_party(Partner, name, people, companies, index):
    if name:
        found = Partner.search([('name', '=', name)], limit=1)
        if found:
            return found
    pool = companies if index % 2 == 0 else people
    return pool[(index * 13) % len(pool)]


def _amount(text):
    digits = re.sub(r'[^0-9]', '', text or '')
    return float(digits) if digits else 0.0


def _date(text, year):
    """«28 августа 2026» → дата.

    Разбирается вручную: месяц в макете написан по-русски словом, и
    штатный разбор дат его не понимает.
    """
    match = re.match(r'(\d{1,2})\s+([а-яё]+)\s+(\d{4})', (text or '').lower())
    if match:
        day, month_name, found_year = match.groups()
        month = MONTHS.get(month_name)
        if month:
            return '%s-%02d-%02d' % (found_year, month, int(day))
    return '%s-01-15' % (year or '2026')


def _make_lines(Line, deal, rnd, index):
    parts = rnd.choice([1, 1, 2, 2, 3])
    if not deal.amount:
        Line.create({
            'deal_id': deal.id, 'name': deal.name,
            'quantity': 1, 'uom_name': 'шт.', 'price_unit': 0,
        })
        return
    remaining = deal.amount
    for offset in range(parts):
        last = offset == parts - 1
        value = remaining if last else round(deal.amount / parts)
        remaining -= value
        Line.create({
            'deal_id': deal.id,
            'sequence': (offset + 1) * 10,
            'name': deal.name if parts == 1 else '%s — часть %s' % (deal.name, offset + 1),
            'quantity': 1,
            'uom_name': 'шт.',
            'price_unit': value,
        })


def _make_payments(Payment, deal, rnd, index):
    """График платежей: у трети сделок — рассрочка, как в макете."""
    parts = rnd.choice([1, 1, 2, 3])
    signed = deal.signed_on
    remaining = deal.amount
    for offset in range(parts):
        last = offset == parts - 1
        value = remaining if last else round(deal.amount / parts)
        remaining -= value
        due = signed.replace(day=min(28, signed.day)) if signed else None
        if due:
            month = due.month + offset
            year = due.year + (month - 1) // 12
            due = due.replace(year=year, month=(month - 1) % 12 + 1)
        paid = deal.state == 'done' or (offset == 0 and deal.state != 'draft')
        Payment.create({
            'deal_id': deal.id,
            'name': 'Платёж %s из %s' % (offset + 1, parts) if parts > 1 else 'Оплата по договору',
            'due_on': due,
            'amount': value,
            'state': 'paid' if paid else 'planned',
            'paid_on': due if paid else False,
        })


def _make_reviews(Review, deal, row, index):
    """Отзывы по правилу платформы: раскрываются, когда написаны оба.

    У части сделок отзыв один — они и должны выглядеть как ждущие
    второго. Подставлять оба всюду значило бы спрятать состояние, ради
    которого правило и заведено.
    """
    outcome = row.get('outcome')
    if outcome == 'pending':
        pairs = [(deal.party_a_id, deal.party_b_id)]
        rating, texts = '4', REVIEW_GOOD
    elif outcome == 'negative':
        pairs = [(deal.party_a_id, deal.party_b_id), (deal.party_b_id, deal.party_a_id)]
        rating, texts = '2', REVIEW_BAD
    elif outcome == 'positive':
        pairs = [(deal.party_a_id, deal.party_b_id), (deal.party_b_id, deal.party_a_id)]
        rating, texts = '5', REVIEW_GOOD
    else:
        return
    # У каждой пятой завершённой сделки отзыв один — она и должна
    # выглядеть как ждущая второго. Иначе состояние «ждём отзывов», ради
    # которого правило раскрытия и заведено, на стенде не увидеть.
    if len(pairs) == 2 and index % 5 == 0:
        pairs = pairs[:1]

    for offset, (author, target) in enumerate(pairs):
        Review.create({
            'deal_id': deal.id,
            'author_id': author.id,
            'target_id': target.id,
            'rating': rating,
            'body': texts[(index + offset) % len(texts)],
        })


def _extra_rows(rows, extra, rnd):
    """Добор сверх макета — по тому же основанию, что и в каталогах."""
    titles = [
        'Аренда трактора на сезон', 'Поставка досок обрезных',
        'Ремонт кровли склада', 'Партия саженцев яблони',
        'Услуги ветеринара на выезде', 'Обмен: мёд на пиломатериал',
        'Помол зерна давальческий', 'Перевозка сена',
        'Монтаж системы полива', 'Пошив рабочей одежды',
        'Изготовление ульев', 'Услуги сварщика',
        'Аренда холодильной камеры', 'Партия картофеля',
        'Разработка сайта кооператива',
    ]
    cities = sorted({row['city'] for row in rows if row['city']})
    extras = []
    for i in range(extra):
        source = rows[(i * 13) % len(rows)]
        row = dict(source)
        row['name'] = titles[i % len(titles)]
        row['city'] = cities[(i * 3) % len(cities)] if cities else ''
        row['party'] = ''
        extras.append(row)
    return extras
