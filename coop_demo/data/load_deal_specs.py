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
