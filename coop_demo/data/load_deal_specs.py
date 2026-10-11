# -*- coding: utf-8 -*-
"""Спецификация и график платежей у согласованных сделок.

Замечание владельца 11.10.2026: «в спецификации пусто, а сделка
завершена как так?». На стенде 547 сделок из 692 были без строк, из
завершённых — 96 из 213: спецификацию писал только загрузчик из
deals.json, а примеры, склады, отклики и CRM заводили сделку без неё.

С того же дня согласовать сделку без спецификации нельзя. Проход
дописывает её сделкам, которые уже прошли согласование мимо кнопки, и
график платежей тем, где платят деньгами. Сумма строк сходится с суммой
сделки, платежи — тоже; состояния платежей следуют за стадией сделки.
Повторный прогон не трогает сделку, у которой строки или платежи уже
есть.
"""
import hashlib
import logging
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

AGREED = ('agreed', 'active', 'acceptance', 'done', 'disputed', 'cancelled')
# Способы, где за переданное платят деньгами. Обмен, дар, взаимный кредит
# и доля в проекте рассчитываются иначе — графика платежей у них нет.
MONEY_WAYS = ('sale', 'purchase', 'batch', 'rent', 'service', 'job')

UNITS = {
    'resource': ('шт.', (1, 2, 4, 5, 10, 20, 25, 50, 100)),
    'service': ('ч', (4, 8, 10, 16, 20, 40)),
    'work': ('мес.', (1, 2, 3)),
    'project': ('вклад', (1,)),
    'credit': ('лимит', (1,)),
}
EXTRAS = {
    'resource': 'Доставка',
    'service': 'Выезд специалиста',
    'work': 'Премия по итогам',
}


def _bucket(rec_id, salt):
    digest = hashlib.md5(('deal-spec:%s:%s' % (rec_id, salt)).encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _subject_name(deal):
    item = {
        'resource': deal.resource_id,
        'service': deal.skill_offer_id,
        'work': deal.vacancy_id,
        'project': deal.project_id,
    }.get(deal.subject)
    return (item and item.display_name) or deal.name


def _split(amount, quantities, rec_id):
    """Количество и цена, дающие ровно сумму: перебор делителей."""
    fits = [q for q in quantities
            if abs(round(amount / q, 2) * q - amount) < 0.005]
    if not fits:
        return 1.0, amount
    qty = fits[int(_bucket(rec_id, 'qty') * len(fits)) % len(fits)]
    return float(qty), round(amount / qty, 2)


def _lines(deal):
    unit, quantities = UNITS.get(deal.subject, ('шт.', (1,)))
    name = _subject_name(deal)
    if deal.resource_id and getattr(deal.resource_id, 'uom_label', False):
        unit = deal.resource_id.uom_label
    amount = deal.amount or 0.0
    extra = EXTRAS.get(deal.subject)
    lines = []
    # Каждая четвёртая сделка с деньгами — в две строки: основное и
    # сопутствующее, как в живых договорах.
    if extra and amount >= 2000 and _bucket(deal.id, 'two') < 0.25:
        side = round(amount * (0.05 + 0.1 * _bucket(deal.id, 'side')), -1)
        lines.append({'name': extra, 'quantity': 1.0, 'uom_name': 'усл.',
                      'price_unit': side, 'sequence': 20})
        amount -= side
    qty, price = _split(amount, quantities, deal.id)
    lines.insert(0, {'name': name, 'quantity': qty, 'uom_name': unit,
                     'price_unit': price, 'sequence': 10})
    return lines


def _schedule(deal, today):
    """Платежи по сделке: одной суммой, с предоплатой или помесячно."""
    start = deal.signed_on or deal.create_date.date()
    amount = deal.amount
    if deal.way == 'rent':
        parts = 3
        names = ['Аренда, %s-й месяц' % (i + 1) for i in range(parts)]
        offsets = [30 * i for i in range(parts)]
    elif _bucket(deal.id, 'pre') < 0.4:
        parts = 2
        names = ['Предоплата', 'Окончательный расчёт']
        offsets = [3, 14 + int(_bucket(deal.id, 'late') * 30)]
    else:
        parts = 1
        names = ['Оплата по договору']
        offsets = [5 + int(_bucket(deal.id, 'due') * 20)]
    if parts == 2:
        first = round(amount * 0.3, 2)
        sums = [first, round(amount - first, 2)]
    else:
        each = round(amount / parts, 2)
        sums = [each] * (parts - 1) + [round(amount - each * (parts - 1), 2)]

    payer, payee = deal._coop_payer_payee()
    rows = []
    for index, (name, offset, value) in enumerate(zip(names, offsets, sums)):
        due = start + timedelta(days=offset)
        if deal.state == 'cancelled':
            state = 'paid' if index == 0 and parts > 1 and _bucket(deal.id, 'refund') < 0.3 \
                else 'cancelled'
        elif deal.state == 'done':
            state = 'paid'
        elif deal.state in ('active', 'acceptance', 'disputed') and index == 0:
            state = 'paid'
        else:
            state = 'overdue' if due < today else 'planned'
        paid_on = False
        if state == 'paid':
            paid_on = min(due + timedelta(days=int(_bucket(deal.id, index) * 4) - 1),
                          deal.closed_on or today, today)
        rows.append({
            'deal_id': deal.id,
            'name': name,
            'due_on': due,
            'amount': value,
            'payer_id': payer.id,
            'payee_id': payee.id,
            'state': state,
            'paid_on': paid_on,
        })
    return rows


def load_deal_specs(env):
    Deal = env['coop.deal'].sudo().with_context(
        tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    Line = env['coop.deal.line'].sudo()
    Payment = env['coop.deal.payment'].sudo().with_context(
        tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    today = fields.Date.context_today(Deal)

    deals = Deal.search([('state', 'in', AGREED)], order='id')
    lines = payments = 0
    for deal in deals:
        if deal.state == 'cancelled' and not deal.signed_on:
            continue  # отменена до согласования — спецификации и не было
        try:
            with env.cr.savepoint():
                if not deal.line_ids:
                    Line.create([dict(vals, deal_id=deal.id) for vals in _lines(deal)])
                    lines += 1
                if (deal.way in MONEY_WAYS and deal.amount > 0
                        and not deal.payment_ids):
                    Payment.create(_schedule(deal, today))
                    payments += 1
        except Exception:
            _logger.exception('Сделка %s: спецификация не дописана', deal.number)
    _logger.info('Спецификация дописана сделкам: %s, график платежей: %s',
                 lines, payments)


DOPLATA = 'Доплата за разницу в стоимости'


def _paid_on(deal, due, salt, today):
    return min(due + timedelta(days=int(_bucket(deal.id, salt) * 4) - 1),
               deal.closed_on or today, today)


def tidy_payment_schedules(env):
    """Графики платежей — как у действующей площадки.

    Замечание владельца 11.10.2026 (сделка 327: обмен на 3 200 ₽ с
    просроченным платежом 5 096 ₽ и отменённым 28 649 ₽). Замер в тот же
    день: 170 из 213 завершённых сделок с неоплаченными платежами, у 39
    сделок платежи не сходятся с суммой, у 66 обменов денежные платежи.

    - Обмен и дар деньгами не платятся: платежи снимаются, у каждой
      пятой сделки обмена остаётся доплата за разницу в стоимости.
    - Платежи, кроме отменённых, сходятся с суммой сделки; отменённый не
      больше суммы сделки.
    - Завершённая сделка оплачена; долг после акта — у каждой восьмой.
    - У отменённой сделки неоплаченное отменено.
    """
    Deal = env['coop.deal'].sudo().with_context(
        tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    Payment = env['coop.deal.payment'].sudo().with_context(
        tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    today = fields.Date.context_today(Deal)
    nominal = 'nominal_hold_ids' in Payment._fields
    fixed = 0
    for deal in Deal.search([('payment_ids', '!=', False)], order='id'):
        payments = deal.payment_ids.sorted(lambda p: (p.due_on, p.id))
        if nominal and payments.nominal_hold_ids:
            continue  # деньги на номинальном счёте — их график не трогаем
        before = [(p.amount, p.state) for p in payments]
        try:
            with env.cr.savepoint():
                if deal.way in ('exchange', 'gift'):
                    _tidy_barter(deal, payments, Payment, today)
                else:
                    _tidy_money(deal, payments, Payment, today)
                after = [(p.amount, p.state) for p in deal.payment_ids.sorted(
                    lambda p: (p.due_on, p.id))]
                fixed += before != after
        except Exception:
            _logger.exception('Сделка %s: график не приведён', deal.number)
    _logger.info('Графики платежей приведены в порядок: %s сделок', fixed)


def _tidy_barter(deal, payments, Payment, today):
    payments.filtered(lambda p: p.name != DOPLATA).unlink()
    keep = deal.way == 'exchange' and deal.amount > 0 and _bucket(deal.id, 'dop') < 0.2
    if not keep or deal.payment_ids or deal.state in ('lead', 'draft'):
        return
    payer, payee = deal._coop_payer_payee()
    due = (deal.signed_on or deal.create_date.date()) + timedelta(days=7)
    if deal.state == 'cancelled':
        state = 'cancelled'
    elif deal.state == 'done':
        state = 'paid'
    else:
        state = 'overdue' if due < today else 'planned'
    Payment.create({
        'deal_id': deal.id,
        'name': DOPLATA,
        'due_on': due,
        'amount': round(deal.amount * (0.1 + 0.15 * _bucket(deal.id, 'dsum')), -1) or 100.0,
        'payer_id': payer.id,
        'payee_id': payee.id,
        'state': state,
        'paid_on': _paid_on(deal, due, 'dop', today) if state == 'paid' else False,
    })


def _tidy_money(deal, payments, Payment, today):
    currency = deal.currency_id
    live = payments.filtered(lambda p: p.state != 'cancelled')
    if (not live and deal.amount > 0 and deal.way in MONEY_WAYS
            and deal.state not in ('lead', 'draft', 'cancelled')):
        # Остались одни отменённые — договорённость об оплате всё же была.
        Payment.create(_schedule(deal, today))
        return
    total = sum(live.mapped('amount'))
    if live and deal.amount > 0 and currency.compare_amounts(total, deal.amount):
        # Пропорционально, остаток округления — последнему платежу.
        rest = deal.amount
        for payment in live[:-1]:
            value = currency.round(payment.amount * deal.amount / total)
            payment.amount = value
            rest -= value
        live[-1].amount = currency.round(rest)
    for payment in payments.filtered(lambda p: p.state == 'cancelled'):
        if deal.amount > 0 and payment.amount > deal.amount:
            payment.amount = currency.round(deal.amount * 0.3)

    open_ = live.filtered(lambda p: p.state in ('planned', 'overdue'))
    if deal.state == 'cancelled':
        open_.write({'state': 'cancelled'})
    elif deal.state == 'done' and open_:
        debt = open_[-1:] if _bucket(deal.id, 'debt') < 0.125 else open_.browse()
        for payment in open_ - debt:
            payment.write({'state': 'paid',
                           'paid_on': _paid_on(deal, payment.due_on, payment.id, today)})
        for payment in debt:
            payment.state = 'overdue' if payment.due_on < today else 'planned'
