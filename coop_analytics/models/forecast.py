# -*- coding: utf-8 -*-
"""«Прогноз и план» — слой 4 «Аналитики» (решения 420, 423).

Свой тренд и план на экранах платформы, без mis_builder (решение 423):

- **факт** — помесячно за 12 месяцев по показателям участника (или
  организации, от имени которой он действует): приход и расход денег,
  сделки, вклады в проекты, активность;
- **прогноз** — продолжение тренда: прямая по 12 полным месяцам методом
  наименьших квадратов на 6 месяцев вперёд, не ниже нуля. Меньше трёх
  месяцев с данными — прямой не строим, берём средний месяц;
- **план** — цель на месяц, которую ставит сам участник; «план — факт» и
  темп текущего месяца («к концу месяца при таком темпе ≈ …»).

Прогноз — расчёт по своим же данным, а не обещание: так и подписано на
экране.
"""
import calendar
from collections import defaultdict
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

METRICS = [
    ('money_in', 'Приход денег'),
    ('money_out', 'Расход денег'),
    ('deals_amount', 'Сумма сделок'),
    ('deals_count', 'Число сделок'),
    ('contributions', 'Вклады в проекты'),
    ('activity', 'Активность'),
]
# unit: rub / count; better: up — больше лучше, down — меньше лучше (лимит).
METRIC_META = {
    'money_in': {'unit': 'rub', 'better': 'up',
                 'hint': 'Проведённые поступления в кошелёк: пополнения, оплаты по сделкам, переводы.'},
    'money_out': {'unit': 'rub', 'better': 'down',
                  'hint': 'Проведённые списания. План здесь — лимит расходов на месяц.'},
    'deals_amount': {'unit': 'rub', 'better': 'up',
                     'hint': 'Сумма сделок, заключённых в месяце (без черновиков и отменённых).'},
    'deals_count': {'unit': 'count', 'better': 'up',
                    'hint': 'Сколько сделок заключено в месяце.'},
    'contributions': {'unit': 'rub', 'better': 'up',
                      'hint': 'Оценка вкладов в проекты, принятых инициаторами, — по дате предложения.'},
    'activity': {'unit': 'count', 'better': 'up',
                 'hint': 'Записи, сообщения, комментарии, сделки, уроки, обмены и вклады.'},
}
MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
HISTORY = 12
AHEAD = 6


def _month_start(value):
    return date(value.year, value.month, 1)


def _shift(month, n):
    y, m = divmod(month.year * 12 + month.month - 1 + n, 12)
    return date(y, m + 1, 1)


def _trend(values):
    """Прямая по точкам (МНК) → функция от номера месяца. Меньше трёх
    ненулевых месяцев — средний месяц."""
    n = len(values)
    if n == 0:
        return lambda _x: 0.0, 'none'
    if sum(1 for v in values if v) < 3:
        avg = sum(values) / n
        return lambda _x: avg, 'average'
    xs = range(n)
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    den = sum((x - mean_x) ** 2 for x in xs) or 1
    slope = num / den
    base = mean_y - slope * mean_x
    return (lambda x: max(0.0, base + slope * x)), 'trend'


class CoopAnalyticsPlan(models.Model):
    _name = 'coop.analytics.plan'
    _description = 'План на месяц'
    _order = 'month desc, metric'

    partner_id = fields.Many2one('res.partner', string='Чей план', required=True, index=True,
                                 ondelete='cascade')
    metric = fields.Selection(METRICS, string='Показатель', required=True, index=True)
    month = fields.Date(string='Месяц', required=True, index=True,
                        help='Первое число месяца.')
    target = fields.Float(string='Цель', required=True, digits=(16, 2))
    note = fields.Char(string='Пометка')

    _plan_unique = models.Constraint(
        'unique(partner_id, metric, month)',
        'На один месяц по одному показателю — один план.',
    )

    @api.constrains('target')
    def _check_target(self):
        for record in self:
            if record.target < 0:
                raise ValidationError(_('План не может быть меньше нуля.'))


class CoopForecast(models.AbstractModel):
    _name = 'coop.forecast'
    _description = 'Прогноз и план'

    # ── чей экран ────────────────────────────────────────────────────
    def _actors(self):
        user = self.env.user
        actors = user.coop_actor_partner_ids if 'coop_actor_partner_ids' in user._fields else user.partner_id
        me = user.partner_id
        return me, (me | actors)

    def _partner(self, partner_id):
        me, actors = self._actors()
        if not partner_id:
            return me
        partner = self.env['res.partner'].browse(int(partner_id))
        if partner not in actors:
            raise AccessError(_('Смотреть и планировать можно только за себя и за организации, '
                                'от имени которых вы действуете.'))
        return partner

    # ── факт по месяцам ──────────────────────────────────────────────
    def _series(self, partner, metric, start, end):
        """{первое число месяца: значение} за [start, end)."""
        env = self.env
        out = defaultdict(float)
        if metric in ('money_in', 'money_out'):
            sign = ('amount', '>', 0) if metric == 'money_in' else ('amount', '<', 0)
            rows = env['coop.wallet.movement'].sudo()._read_group(
                [('partner_id', '=', partner.id), ('state', '=', 'confirmed'), sign,
                 ('date', '>=', start), ('date', '<', end)],
                ['date:month'], ['amount:sum'])
            for month, amount in rows:
                out[_month_start(month)] += abs(amount or 0)
        elif metric in ('deals_amount', 'deals_count'):
            rows = env['coop.deal'].sudo()._read_group(
                ['|', ('party_a_id', '=', partner.id), ('party_b_id', '=', partner.id),
                 ('state', 'not in', ('lead', 'draft', 'cancelled')),
                 ('signed_on', '>=', start), ('signed_on', '<', end)],
                ['signed_on:month'], ['amount:sum', '__count'])
            for month, amount, count in rows:
                out[_month_start(month)] += (amount or 0) if metric == 'deals_amount' else count
        elif metric == 'contributions':
            rows = env['coop.project.contribution'].sudo()._read_group(
                [('partner_id', '=', partner.id), ('state', 'in', ('accepted', 'released', 'returned')),
                 ('offered_on', '>=', start), ('offered_on', '<', end)],
                ['offered_on:month'], ['value:sum'])
            for month, value in rows:
                out[_month_start(month)] += value or 0
        elif metric == 'activity':
            rows = env['coop.account.activity'].sudo()._read_group(
                [('partner_id', '=', partner.id),
                 ('date', '>=', fields.Datetime.to_datetime(start)),
                 ('date', '<', fields.Datetime.to_datetime(end))],
                ['date:month'], ['count:sum'])
            for month, count in rows:
                out[_month_start(month)] += count or 0
        return out

    # ── снимок экрана ────────────────────────────────────────────────
    @api.model
    def overview(self, partner_id=None):
        partner = self._partner(partner_id)
        me, actors = self._actors()
        today = fields.Date.context_today(self)
        current = _month_start(today)
        first = _shift(current, -HISTORY)
        last = _shift(current, AHEAD)
        days_in = calendar.monthrange(today.year, today.month)[1]
        share_of_month = today.day / days_in

        plans = defaultdict(dict)
        for plan in self.env['coop.analytics.plan'].sudo().search(
                [('partner_id', '=', partner.id), ('month', '>=', first), ('month', '<', last)]):
            plans[plan.metric][_month_start(plan.month)] = plan.target

        metrics = []
        for key, label in METRICS:
            meta = METRIC_META[key]
            series = self._series(partner, key, first, _shift(current, 1))
            history = [series.get(_shift(first, i), 0.0) for i in range(HISTORY)]
            line, mode = _trend(history)
            fact_now = series.get(current, 0.0)
            months = []
            for i in range(HISTORY + AHEAD):
                month = _shift(first, i)
                is_past = month < current
                row = {
                    'key': month.isoformat()[:7],
                    'label': '%s %02d' % (MONTHS[month.month - 1], month.year % 100),
                    'past': is_past, 'current': month == current,
                    'fact': history[i] if is_past else (fact_now if month == current else None),
                    'forecast': None if is_past else line(i),
                    'plan': plans[key].get(month),
                }
                if is_past and row['plan'] is not None:
                    row['done'] = (row['fact'] >= row['plan']) if meta['better'] == 'up' \
                        else (row['fact'] <= row['plan'])
                months.append(row)
            plan_now = plans[key].get(current)
            pace = fact_now / share_of_month if share_of_month else fact_now
            past_plans = [m for m in months if m['past'] and m['plan'] is not None]
            metrics.append({
                'key': key, 'label': label, 'unit': meta['unit'], 'better': meta['better'],
                'hint': meta['hint'], 'mode': mode,
                'months': months,
                'now': {
                    'fact': fact_now, 'plan': plan_now, 'pace': pace,
                    'forecast': line(HISTORY),
                    'pct': round(fact_now / plan_now * 100) if plan_now else None,
                    'days_left': days_in - today.day,
                },
                'avg': sum(history) / HISTORY,
                'plans_done': sum(1 for m in past_plans if m.get('done')),
                'plans_total': len(past_plans),
            })
        return {
            'today': today.isoformat(),
            'partner': {'id': partner.id, 'name': partner.name},
            'partners': [{'id': p.id, 'name': p.name, 'me': p == me} for p in (me | actors)],
            'metrics': metrics,
        }

    @api.model
    def set_plan(self, partner_id, metric, month, target, repeat=1):
        """План на `repeat` месяцев подряд, начиная с `month` («2026-10»).
        Пустая цель (None) снимает план."""
        partner = self._partner(partner_id)
        if metric not in dict(METRICS):
            raise ValidationError(_('Нет такого показателя.'))
        Plan = self.env['coop.analytics.plan'].sudo()
        start = date(int(month[:4]), int(month[5:7]), 1)
        for i in range(max(1, min(int(repeat or 1), 12))):
            when = _shift(start, i)
            existing = Plan.search([('partner_id', '=', partner.id), ('metric', '=', metric),
                                    ('month', '=', when)], limit=1)
            if target in (None, False, ''):
                existing.unlink()
            elif existing:
                existing.target = float(target)
            else:
                Plan.create({'partner_id': partner.id, 'metric': metric, 'month': when,
                             'target': float(target)})
        return True

    # ── наполнение ───────────────────────────────────────────────────
    @api.model
    def _seed_main_plans(self, login='dashkevich'):
        """Планы главного участника витрины — чтобы «план — факт» было на
        чём видеть (правило объёма данных, решение 407). Прогон один: план
        у него уже есть — выходит. Цели — от его же среднего месяца с
        разбросом, часть месяцев без плана: так и бывает."""
        user = self.env['res.users'].sudo().search([('login', '=', login)], limit=1)
        if not user:
            return 0
        partner = user.partner_id
        Plan = self.env['coop.analytics.plan'].sudo()
        if Plan.search_count([('partner_id', '=', partner.id)]):
            return 0
        import random
        rnd = random.Random('plans:%s' % partner.id)
        today = fields.Date.context_today(self)
        current = _month_start(today)
        first = _shift(current, -HISTORY)
        made = 0
        for key, _label in METRICS:
            series = self._series(partner, key, first, _shift(current, 1))
            values = [series.get(_shift(first, i), 0.0) for i in range(HISTORY)]
            floor = 3 if METRIC_META[key]['unit'] == 'count' else 20000
            base = max(sum(values) / HISTORY, floor)
            for i in range(-9, AHEAD):
                if rnd.random() < 0.2:
                    continue
                target = base * rnd.uniform(0.8, 1.35)
                if METRIC_META[key]['unit'] == 'count':
                    target = max(1, round(target))
                else:
                    target = round(target / 1000) * 1000 or 1000
                Plan.create({'partner_id': partner.id, 'metric': key,
                             'month': _shift(current, i), 'target': target})
                made += 1
        return made
