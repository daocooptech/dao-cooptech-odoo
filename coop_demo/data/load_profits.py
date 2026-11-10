# -*- coding: utf-8 -*-
"""Объявления прибыли проектов и выплаты по долям (задача 387, кусок 5). Идемпотентно.

Коммерческие проекты и ДАО с принятыми вкладами получают от одного до двух
объявлений за кварталы с третьего квартала 2025 года. Состояния — все:
черновик (часть уже рассчитана), объявлена, выплачена, спорная,
отменена. Старые кварталы чаще выплачены; свежие — объявлены или ещё
черновик. Выплата идёт настоящим действием `action_pay`: движения по
кошелькам заводятся по тем же правилам, что и в работе, но без
извещений (флаг в контексте) — извещения демо строит другой загрузчик.
Даты объявления и выплаты задним числом: после конца квартала.

Повторный прогон ничего не удваивает: ключ — проект и период.
"""
import logging
import random
from datetime import date, datetime, timedelta

_logger = logging.getLogger(__name__)

QUARTERS = [
    (date(2025, 7, 1), date(2025, 9, 30)),
    (date(2025, 10, 1), date(2025, 12, 31)),
    (date(2026, 1, 1), date(2026, 3, 31)),
    (date(2026, 4, 1), date(2026, 6, 30)),
    (date(2026, 7, 1), date(2026, 9, 30)),
]
# Вес состояния: старый квартал / свежий.
OLD = [('paid', 62), ('disputed', 10), ('cancelled', 12), ('declared', 10), ('draft', 6)]
FRESH = [('declared', 36), ('draft', 28), ('paid', 22), ('disputed', 6), ('cancelled', 8)]
DISPUTES = [
    'Вкладчик не согласен с суммой: считает, что из расчёта выпали расходы на аренду.',
    'Спор о периоде: часть выручки относится к следующему кварталу.',
    'Не учтён вклад, принятый в последние дни периода.',
    'Вкладчики просят пересчитать доли после возврата одного из вкладов.',
    'Сумма объявлена без пояснений, запрошена выписка по счёту проекта.',
]
NOTES = [
    'Прибыль по итогам квартала после оплаты расходов проекта.',
    'Распределяем половину чистой прибыли, остальное остаётся в обороте.',
    'Выручка по заказам квартала за вычетом закупок и аренды.',
    'Прибыль от продажи первой партии.',
    False,
]


def _pick(rnd, table):
    return rnd.choices([s for s, _ in table], weights=[w for _, w in table])[0]


def load_profits(env):
    if 'coop.project.profit' not in env:
        return 0
    Profit = env['coop.project.profit'].sudo().with_context(
        tracking_disable=True, mail_create_nolog=True,
        mail_notrack=True, coop_skip_profit_notify=True)
    projects = env['coop.project'].sudo().search(
        [('kind', 'in', ['commercial', 'dao'])], order='id')
    now = datetime.utcnow()
    made = 0
    for project in projects:
        accepted = project.contribution_ids.filtered(
            lambda c: c.state == 'accepted' and c.share_tokens)
        if not accepted:
            continue
        # Свой поток случайных чисел у каждого проекта: повторный прогон
        # пропускает заведённое и не сдвигает выбор у остальных.
        rnd = random.Random(387_000 + project.id)
        collected = sum(accepted.mapped('value'))
        count = rnd.choice([1, 2, 2])
        quarters = sorted(rnd.sample(range(len(QUARTERS)), count))
        for number in quarters:
            start, end = QUARTERS[number]
            if Profit.search_count([('project_id', '=', project.id),
                                    ('period_from', '=', start),
                                    ('period_to', '=', end)]):
                continue
            state = _pick(rnd, FRESH if number >= 3 else OLD)
            amount = max(30000, round(collected * rnd.uniform(0.03, 0.18), -2))
            declared_on = datetime.combine(
                end + timedelta(days=rnd.randint(4, 24)),
                datetime.min.time()) + timedelta(hours=rnd.randint(8, 19))
            if declared_on > now:
                declared_on = now - timedelta(days=rnd.randint(1, 6))
            paid_gap = timedelta(days=rnd.randint(1, 9), hours=rnd.randint(0, 6))
            note = rnd.choice(NOTES)
            dispute = rnd.choice(DISPUTES)
            compute_draft = rnd.random() < 0.5
            try:
                with env.cr.savepoint():
                    profit = Profit.create({
                        'project_id': project.id,
                        'period_from': start, 'period_to': end,
                        'amount': amount, 'note': note,
                    })
                    if state == 'draft':
                        if compute_draft:
                            profit.action_compute()
                    else:
                        profit.action_declare()
                        profit.write({'declared_on': declared_on,
                                      'declared_by_id': project.partner_id.id})
                        if state == 'paid':
                            profit.action_pay()
                            paid_on = min(declared_on + paid_gap, now)
                            profit.write({'paid_on': paid_on})
                            profit.line_ids.movement_id.write(
                                {'date': paid_on.date()})
                        elif state == 'disputed':
                            profit.action_dispute()
                            profit.dispute_reason = dispute
                        elif state == 'cancelled':
                            profit.action_cancel()
                made += 1
            except Exception:
                _logger.exception('Прибыль проекта %s за %s не заведена',
                                  project.display_name, start)
    _logger.info('Прибыль проектов: объявлений заведено %s', made)
    return made
