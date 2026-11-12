# -*- coding: utf-8 -*-
"""Даты демо, которые устарели (решения владельца 654 и 655, 12.11.2026).

Аукционы. Загрузчик ставил окончание от дня прогона, и к ноябрю все 105
торгов кончились — в каталоге не было ни одного идущего. Здесь лоты
раскладываются заново от сегодняшнего дня: около 40 % идут (часть
кончается в ближайшие часы, остальные — до полутора месяцев вперёд),
около 15 % скоро начнутся, около 37 % завершены за последние четыре
месяца, остальные отменены. Ставки идущих и прошедших ложатся внутрь
срока торга; у тех, что ещё не начались, ставок нет.

Сделки dashkevich. Почти все были заключены в июле–октябре 2026, и
аналитика «сделок в месяц» показывала восемь пустых месяцев подряд.
Здесь даты сделки сдвигаются назад целиком (заключена, закрыта, акт,
спор, платежи) так, что заключение разнесено на 12 месяцев с плавным
ростом к сегодняшнему дню. Сдвиг только назад — прошлое остаётся
прошлым, порядок дат внутри сделки не меняется.
"""
import calendar
import logging
import random
from datetime import date, timedelta

from odoo import fields

_logger = logging.getLogger(__name__)


def refresh_auction_dates(env):
    Auction = env['coop.auction'].sudo().with_context(
        tracking_disable=True, mail_notrack=True)
    now = fields.Datetime.now()
    counts = {}
    for auction in Auction.search([], order='id'):
        rnd = random.Random('auction-refresh:%s' % auction.id)
        roll = rnd.random()
        if roll < 0.40:
            kind = 'running'
            hours = rnd.choice([rnd.randint(1, 3)] + [rnd.randint(6, 24 * 45)] * 6)
            end = now + timedelta(hours=hours, minutes=rnd.randint(0, 59))
            start = now - timedelta(days=rnd.randint(1, 10), hours=rnd.randint(0, 23))
        elif roll < 0.55:
            kind = 'draft'
            start = now + timedelta(days=rnd.randint(1, 30), hours=rnd.randint(0, 23))
            end = start + timedelta(days=rnd.randint(3, 14))
        else:
            kind = 'cancelled' if roll >= 0.92 else 'past'
            end = now - timedelta(days=rnd.randint(1, 120), hours=rnd.randint(0, 23))
            start = end - timedelta(days=rnd.randint(3, 14))

        if kind == 'draft':
            # Ставки демо — мимо `unlink` модели: он законно запрещает
            # снимать ставки, а у торга, что ещё не начался, их быть не может.
            env.cr.execute('DELETE FROM coop_auction_bid WHERE auction_id = %s',
                           (auction.id,))
            auction.invalidate_recordset()
        vals = {'date_start': start, 'date_end': end}
        if kind in ('running', 'draft'):
            vals.update(state=kind, winner_id=False)
        elif kind == 'cancelled':
            vals['state'] = 'cancelled'
        auction.write(vals)

        # Ставки — внутри срока торга, по порядку возрастания номера.
        bids = auction.bid_ids.sorted('id')
        if bids:
            last = min(end, now) - timedelta(minutes=5)
            span = max((last - start).total_seconds(), 60)
            moments = sorted(int(span * rnd.random()) for _ in bids)
            for bid, offset in zip(bids, moments):
                env.cr.execute(
                    'UPDATE coop_auction_bid SET create_date = %s, write_date = %s '
                    'WHERE id = %s',
                    (start + timedelta(seconds=offset),
                     start + timedelta(seconds=offset), bid.id))

        if kind == 'past' and auction.state in ('running', 'draft'):
            auction.invalidate_recordset()
            auction.action_finish()
        counts[kind] = counts.get(kind, 0) + 1
    env.invalidate_all()
    _logger.info('Аукционы освежены: %s', counts)


def _month_start(day, back):
    year, month = day.year, day.month - back
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


DEAL_DATE_FIELDS = ('signed_on', 'closed_on', 'funnel_date',
                    'act_confirmed_on', 'dispute_resolved_on')


def spread_deal_dates(env, login='dashkevich'):
    partner = env['res.users'].sudo().search([('login', '=', login)]).partner_id
    if not partner:
        return
    cr = env.cr
    today = fields.Date.today()
    # Сделки старше окна в двенадцать месяцев не трогаем и в раскладку не
    # берём: иначе они занимали первые места и самый ранний месяц окна
    # оставался пустым (замер на стенде 12.11: декабрь 2025 — ноль).
    cr.execute(
        'SELECT id, signed_on FROM coop_deal '
        'WHERE signed_on >= %s AND (party_a_id = %s OR party_b_id = %s) '
        'ORDER BY signed_on, id',
        (_month_start(today, 11), partner.id, partner.id))
    rows = cr.fetchall()
    if not rows:
        return
    # Месяц m = 0 — одиннадцать месяцев назад, m = 11 — текущий; вес
    # растёт к сегодняшнему дню, пустых месяцев нет.
    weights = [1 + 0.2 * m for m in range(12)]
    total = sum(weights)
    bounds, acc = [], 0.0
    for weight in weights:
        acc += weight / total
        bounds.append(acc)
    moved = 0
    count = len(rows)
    for rank, (deal_id, signed_on) in enumerate(rows):
        quantile = (rank + 0.5) / count
        month = next(m for m, bound in enumerate(bounds) if quantile <= bound)
        first = _month_start(today, 11 - month)
        last_day = calendar.monthrange(first.year, first.month)[1]
        if month == 11:
            last_day = max(1, today.day - 1)
        rnd = random.Random('deal-spread:%s' % deal_id)
        target = first.replace(day=rnd.randint(1, last_day))
        delta = (min(target, signed_on) - signed_on).days
        if not delta:
            continue
        sets = ', '.join("%s = %s + %%s" % (name, name) for name in DEAL_DATE_FIELDS)
        cr.execute(
            'UPDATE coop_deal SET %s, create_date = create_date + make_interval(days => %%s) '
            'WHERE id = %%s' % sets,
            [delta] * len(DEAL_DATE_FIELDS) + [delta, deal_id])
        cr.execute(
            'UPDATE coop_deal_payment SET due_on = due_on + %s, paid_on = paid_on + %s '
            'WHERE deal_id = %s', (delta, delta, deal_id))
        moved += 1
    env.invalidate_all()
    _logger.info('Сделки %s: даты разнесены по году у %s из %s', login, moved, count)
