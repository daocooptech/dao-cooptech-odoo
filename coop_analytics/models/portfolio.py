# -*- coding: utf-8 -*-
"""«Портфель участника» — слой 3 «Аналитики» (решения 420, 421, 422).

Всё, во что человек вложился, одним снимком: паи в кооперативах, вклады в
проекты, пулы фарминга, токены требования, ЦФА, монеты кошелька и
взаиморасчёты по сделкам. Что и как показывать — по заключениям
экономиста и юриста в Матчасти от 27.09 (`coop-economist`,
`legal-counsel`: «Портфель участника»):

- у пая нет доходности, процента и графика будущих выплат (решение 421) —
  взносы, текущий пай, кооперативные выплаты и что пай дал участнику;
- общего итога в рублях нет — четыре раздельных блока (решение 422);
- у вкладов в проекты — доля и возврат, «доходность» не показывается;
- у пулов — «заявленная ставка» раздельно, «начислено — расчётно»;
- у монет — количество и рубли справочно, с источником и датой курса;
- будущие поступления на 12 месяцев: «договорено», «расчётно», отдельно —
  просроченное и то, что придёт натурой.
"""
from collections import defaultdict
from datetime import timedelta
from statistics import median

from odoo import api, fields, models

# Решение 422, п. 4 — пороги экономиста.
TOKEN_PRICE_DAYS = 30
TOKEN_PRICE_MIN_TRADES = 3
REFUND_GRACE_DAYS = 14

PROJECT_KIND_LABELS = {
    'cooperative': 'Кооперативный', 'nonprofit': 'Некоммерческий',
    'commercial': 'Коммерческий', 'dao': 'ДАО',
}
# Что вклад даёт по форме проекта — вместо «доходности» (заключение
# экономиста, раздел А).
PROJECT_KIND_RESULT = {
    'cooperative': 'Доля в результате по укладу, возврат по правилам проекта',
    'nonprofit': 'Безвозвратный вклад в общее дело',
    'commercial': 'Только фактически полученное — без прогноза',
    'dao': 'Токены долей и доля выпуска; в рублях не оценивается',
}
MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Решение 422, п. 4: без срока рассмотрения заявления на выплату пая
    # просрочку по паю не посчитать.
    coop_share_review_days = fields.Integer(
        string='Срок рассмотрения заявления на выплату пая, дней', default=30,
        help='По уставу кооператива. Заявление на выплату или возврат пая, '
             'не рассмотренное за этот срок, в портфеле пайщика отмечается '
             'как просроченное.')


def _sel(record, field):
    return dict(record._fields[field]._description_selection(record.env)).get(record[field], '')


def _q(value):
    """Количество по-русски: «52,4», а не «52.4»."""
    return ('%g' % (value or 0)).replace('.', ',')


def _d(value):
    return fields.Date.to_string(value) if value else ''


class CoopPortfolio(models.AbstractModel):
    _name = 'coop.portfolio'
    _description = 'Портфель участника'

    @api.model
    def snapshot(self):
        me = self.env.user.partner_id
        today = fields.Date.context_today(self)
        months = self._months(today)
        flow = {m['key']: {'contract': 0.0, 'estimate': 0.0, 'out': 0.0} for m in months}
        overdue = {'in': 0.0, 'out': 0.0, 'items': []}
        natural = defaultdict(list)

        def put(when, key, value):
            month = when.strftime('%Y-%m')
            if month in flow:
                flow[month][key] += value

        shares = self._shares(me, today, overdue)
        projects = self._contributions(me, today, flow, overdue, months)
        farm = self._farm(me, today, flow, put)
        tokens = self._tokens(me, today, natural, overdue)
        cfa = self._cfa(me, today, put, natural, overdue)
        crypto = self._crypto(me)
        settlements = self._settlements(me, today, put, overdue)

        valued = [
            ('Пулы фарминга', sum(r['amount_rub'] for r in farm['rows'] if r['state'] == 'active')),
            ('Токены требования', sum(r['value'] or 0 for r in tokens['rows'])),
            ('ЦФА', sum(r['value'] for r in cfa['rows'])),
            ('Монеты кошелька', sum(r['valuation'] for r in crypto['rows'])),
        ]
        valued_total = sum(v for _, v in valued)
        return {
            'today': _d(today),
            'blocks': {
                'shares': shares['totals'],
                'projects': projects['totals'],
                'valued': {
                    'total': valued_total,
                    'parts': [{'label': l, 'value': v,
                               'pct': round(v / valued_total * 100, 1) if valued_total else 0}
                              for l, v in valued if v],
                },
                'settlements': settlements['totals'],
            },
            'shares': shares['rows'],
            'projects': projects['rows'],
            'project_mix': projects['mix'],
            'farm': farm['rows'],
            'tokens': tokens['rows'],
            'cfa': cfa['rows'],
            'crypto': crypto['rows'],
            'payments': settlements['rows'],
            'schedule': {
                'overdue': {'in': overdue['in'], 'out': overdue['out']},
                'overdue_items': sorted(overdue['items'], key=lambda i: i['date'])[:40],
                'months': [dict(m, **flow[m['key']]) for m in months],
                'natural': [{'key': m['key'], 'label': m['label'], 'items': natural.get(m['key'], [])}
                            for m in months if natural.get(m['key'])],
                'requested_shares': shares['requested'],
            },
            'platform': self._platform(today),
        }

    # ── календарь ────────────────────────────────────────────────────
    def _months(self, today):
        out = []
        year, month = today.year, today.month
        for _i in range(12):
            out.append({'key': '%04d-%02d' % (year, month),
                        'label': '%s %02d' % (MONTHS[month - 1], year % 100)})
            month += 1
            if month > 12:
                year, month = year + 1, 1
        return out

    # ── пай ──────────────────────────────────────────────────────────
    def _shares(self, me, today, overdue):
        Account = self.env['coop.share.account'].sudo()
        Deal = self.env['coop.deal'].sudo()
        rows, requested = [], []
        total_balance = total_accrued = total_paid = 0.0
        accounts = Account.search([('partner_id', '=', me.id)], order='joined_on')
        # Действующие — первыми, возвращённые — в конце.
        rank = {'open': 0, 'closing': 1, 'closed': 2}
        for acc in accounts.sorted(lambda a: rank.get(a.state, 3)):
            coop = acc.cooperative_id
            deals = Deal.search(['|', '&', ('party_a_id', '=', me.id), ('party_b_id', '=', coop.id),
                                 '&', ('party_b_id', '=', me.id), ('party_a_id', '=', coop.id),
                                 ('state', '=', 'done')])
            waiting = []
            for move in acc.move_ids.filtered(lambda m: m.state == 'requested'):
                days = (today - move.date).days if move.date else 0
                late = days > (coop.coop_share_review_days or 30)
                item = {'account': coop.name, 'name': move.name or _sel(move, 'kind'),
                        'kind': _sel(move, 'kind'), 'amount': abs(move.amount),
                        'date': _d(move.date), 'days': days, 'late': late}
                waiting.append(item)
                requested.append(item)
                if late:
                    overdue['items'].append({'date': _d(move.date), 'what': 'Заявление на выплату пая — %s' % coop.name,
                                             'amount': abs(move.amount), 'sign': 1, 'kind': 'share',
                                             'note': 'ждёт решения %s дн.' % days})
            if acc.state != 'closed':
                total_balance += acc.balance
            total_accrued += acc.accrued
            total_paid += acc.paid_out
            rows.append({
                'id': acc.id, 'cooperative': coop.name, 'state': acc.state, 'state_label': _sel(acc, 'state'),
                'joined_on': _d(acc.joined_on), 'contributed': acc.contributed, 'balance': acc.balance,
                'entry_fee': acc.entry_fee,
                'accrued': acc.accrued, 'paid_out': acc.paid_out, 'charter_note': acc.charter_note or '',
                'needs_count': len(deals), 'needs_sum': sum(deals.mapped('amount')),
                'review_days': coop.coop_share_review_days or 30, 'waiting': waiting,
            })
        return {
            'rows': rows, 'requested': requested,
            'totals': {'balance': total_balance, 'accrued': total_accrued, 'paid_out': total_paid,
                       'cooperatives': len({r['cooperative'] for r in rows if r['state'] != 'closed'}),
                       'needs_count': sum(r['needs_count'] for r in rows),
                       'needs_sum': sum(r['needs_sum'] for r in rows)},
        }

    # ── вклады в проекты ─────────────────────────────────────────────
    def _contributions(self, me, today, flow, overdue, months):
        Contribution = self.env['coop.project.contribution'].sudo()
        rows = []
        mix = defaultdict(float)
        totals = {'projects': 0, 'value': 0.0, 'labour': 0.0, 'returned': 0.0, 'losses': 0.0,
                  'offered': 0}
        projects = set()
        first_month = months[0]['key']
        for c in Contribution.search([('partner_id', '=', me.id),
                                      ('state', 'in', ('offered', 'accepted', 'released', 'returned'))],
                                     order='offered_on desc, id desc'):
            project = c.project_id
            failed = project.state in ('failed', 'cancelled')
            refund_due = 0.0
            late = False
            if failed and c.kind == 'money' and c.state in ('accepted', 'released'):
                refund_due = c.refund_amount or c.value
                since = project.date_deadline or c.accepted_on or today
                late = (today - since).days > REFUND_GRACE_DAYS
                if late:
                    overdue['in'] += refund_due
                    overdue['items'].append({'date': _d(since), 'what': 'Возврат вклада — %s' % project.name,
                                             'amount': refund_due, 'sign': 1, 'kind': 'project',
                                             'note': 'проект не состоялся, прошло больше %s дн.' % REFUND_GRACE_DAYS})
                else:
                    flow[first_month]['contract'] += refund_due
            if c.state != 'offered':
                projects.add(project.id)
                totals['value'] += c.value
                if c.kind == 'labour':
                    totals['labour'] += c.value
                mix[PROJECT_KIND_LABELS.get(project.kind, 'Другое')] += c.value
            else:
                totals['offered'] += 1
            if c.state == 'returned':
                totals['returned'] += c.refund_amount or c.value
            totals['losses'] += c.unrecovered_amount or 0.0
            rows.append({
                'id': c.id, 'project_id': project.id, 'project': project.name,
                'project_kind': PROJECT_KIND_LABELS.get(project.kind, ''),
                'result': PROJECT_KIND_RESULT.get(project.kind, ''),
                'project_state': _sel(project, 'state'), 'project_state_key': project.state,
                'readiness': project.readiness, 'kind': _sel(c, 'kind'), 'kind_key': c.kind,
                'name': c.name or '', 'value': c.value, 'state': _sel(c, 'state'), 'state_key': c.state,
                'share_tokens': c.share_tokens, 'share_percent': c.share_percent,
                'return_mode': _sel(c, 'return_mode'), 'refund': c.refund_amount,
                'unrecovered': c.unrecovered_amount, 'withdraw_until': _d(c.withdraw_until),
                'refund_due': refund_due, 'late': late,
                'date': _d(c.offered_on or c.accepted_on),
            })
        totals['projects'] = len(projects)
        total_mix = sum(mix.values())
        return {'rows': rows, 'totals': totals,
                'mix': [{'label': k, 'value': v, 'pct': round(v / total_mix * 100, 1) if total_mix else 0}
                        for k, v in sorted(mix.items(), key=lambda kv: -kv[1])]}

    # ── пулы фарминга ────────────────────────────────────────────────
    def _farm(self, me, today, flow, put):
        Stake = self.env['coop.farm.stake'].sudo()
        prices = {}
        rows = []
        now = fields.Datetime.now()
        for stake in Stake.search([('partner_id', '=', me.id)], order='date desc'):
            pool = stake.pool_id
            key = (pool.asset, pool.network_id.id)
            if key not in prices:
                prices[key] = pool._rub_price()
            price = prices[key]
            earned = stake._earned()
            unlock = stake._unlock_date()
            late_flag = ''
            if pool.state == 'raising' and pool.date_deadline and pool.date_deadline < today:
                late_flag = 'Сбор не закрыт в срок: пул не запущен и не возвращён'
            elif pool.state == 'active' and pool.project_id.state in ('frozen', 'failed'):
                late_flag = 'Проект пула %s' % _sel(pool.project_id, 'state').lower()
            if stake.state == 'active':
                # Тело — в месяце разблокировки, доход — помесячно по
                # заявленной ставке до конца пула. Всё «расчётно».
                put(unlock, 'estimate', stake.amount * price)
                end = pool.date_end or unlock
                month_income = stake.amount * (pool.apr or 0) / 100 / 12 * price
                if pool.state == 'active' and month_income:
                    cursor = today.replace(day=1)
                    while cursor <= end:
                        put(cursor, 'estimate', month_income)
                        cursor = (cursor + timedelta(days=32)).replace(day=1)
            rows.append({
                'id': stake.id, 'pool_id': pool.id, 'project': pool.project_id.name,
                'coin': pool._coin_label(), 'amount': stake.amount, 'price_rub': price,
                'amount_rub': stake.amount * price, 'price_at': fields.Datetime.to_string(now)[:16],
                'apr_fee': pool.apr_fee, 'apr_project': pool.apr_project,
                'earned': earned, 'harvested': stake.harvested, 'pending': max(earned - stake.harvested, 0.0),
                'unlock': _d(unlock), 'risk': _sel(pool, 'risk'), 'risk_key': pool.risk,
                'pool_state': _sel(pool, 'state'), 'state': stake.state, 'state_label': _sel(stake, 'state'),
                'flag': late_flag, 'date': fields.Datetime.to_string(stake.date)[:10],
            })
        return {'rows': rows}

    # ── токены требования ────────────────────────────────────────────
    def _token_price(self, claim, today):
        since = fields.Datetime.to_datetime(today - timedelta(days=TOKEN_PRICE_DAYS))
        trades = self.env['coop.token.trade'].sudo().search([
            ('claim_id', '=', claim.id), ('state', '=', 'done'), ('confirmed_on', '>=', since)])
        prices = [t.price_per_unit for t in trades if t.price_per_unit]
        if len(prices) < TOKEN_PRICE_MIN_TRADES:
            return None, len(prices)
        return median(prices), len(prices)

    def _tokens(self, me, today, natural, overdue):
        Holding = self.env['coop.token.holding'].sudo()
        rows = []
        cache = {}
        for h in Holding.search([('partner_id', '=', me.id)]):
            claim = h.claim_id
            left = max((h.quantity or 0) - (h.accepted_quantity or 0), 0.0)
            if claim.id not in cache:
                cache[claim.id] = self._token_price(claim, today)
            price, trades = cache[claim.id]
            late = bool(claim.delivery_date and claim.delivery_date < today and left > 0
                        and claim.state not in ('settled', 'defaulted', 'cancelled'))
            title = claim.resource_id.name or claim.display_name
            if late:
                overdue['items'].append({'date': _d(claim.delivery_date), 'what': 'Поставка — %s' % title,
                                         'amount': 0, 'sign': 1, 'kind': 'token',
                                         'note': '%s %s не поставлено' % (_q(left), claim.unit_label or '')})
            elif left and claim.delivery_date and claim.state not in ('settled', 'defaulted', 'cancelled'):
                natural[claim.delivery_date.strftime('%Y-%m')].append(
                    '%s %s — %s' % (_q(left), claim.unit_label or '', title))
            rows.append({
                'id': h.id, 'claim_id': claim.id, 'title': title, 'quantity': h.quantity,
                'unit': claim.unit_label or '', 'accepted': h.accepted_quantity, 'left': left,
                'delivery_date': _d(claim.delivery_date), 'place': claim.delivery_place or '',
                'issuer': claim.issuer_id.name or '', 'issuer_trust': claim.issuer_id.coop_trust or 0,
                'state': _sel(claim, 'state'), 'state_key': claim.state,
                'price': price, 'trades': trades, 'value': price * left if price is not None else None,
                'late': late,
            })
        rows.sort(key=lambda r: (r['delivery_date'] or '9999'))
        return {'rows': rows}

    # ── ЦФА ──────────────────────────────────────────────────────────
    def _cfa(self, me, today, put, natural, overdue):
        Holding = self.env['coop.cfa.holding'].sudo()
        groups = {}
        for h in Holding.search([('partner_id', '=', me.id)], order='maturity_date'):
            issue = h.issue_id
            key = ('issue', issue.id) if issue else ('ext', h.name, h.operator_id.id)
            g = groups.get(key)
            if not g:
                g = groups[key] = {
                    'name': issue.name if issue else h.name,
                    'operator': (issue.operator_id or h.operator_id).name or '',
                    'rights': _sel(issue, 'rights_kind') if issue else '',
                    'rights_key': issue.rights_kind if issue else '',
                    'collateral': (issue.collateral or 'не обеспечено') if issue else '',
                    'state': _sel(issue, 'state') if issue else 'По данным оператора',
                    'state_key': issue.state if issue else '',
                    'source': _sel(h, 'source'), 'count': 0, 'quantity': 0.0, 'value': 0.0,
                    'maturity': h.maturity_date, 'late': False,
                }
            g['count'] += 1
            g['quantity'] += h.quantity or 0.0
            g['value'] += h.value or 0.0
            if h.maturity_date and (not g['maturity'] or h.maturity_date < g['maturity']):
                g['maturity'] = h.maturity_date
        rows = []
        for g in groups.values():
            mat = g['maturity']
            if g['state_key'] == 'issued' and mat:
                if mat < today:
                    g['late'] = True
                    if g['rights_key'] == 'money_claim':
                        overdue['in'] += g['value']
                    overdue['items'].append({'date': _d(mat), 'what': 'Погашение ЦФА — %s' % g['name'],
                                             'amount': g['value'] if g['rights_key'] == 'money_claim' else 0,
                                             'sign': 1, 'kind': 'cfa', 'note': 'срок погашения прошёл'})
                elif g['rights_key'] == 'money_claim':
                    put(mat, 'contract', g['value'])
                elif g['rights_key'] == 'goods_claim':
                    natural[mat.strftime('%Y-%m')].append('погашение натурой — %s' % g['name'])
            g['maturity'] = _d(mat)
            rows.append(g)
        rows.sort(key=lambda r: (not r['state_key'], r['maturity'] or '9999'))
        return {'rows': rows}

    # ── монеты кошелька ──────────────────────────────────────────────
    def _crypto(self, me):
        Asset = self.env['coop.wallet.asset'].sudo()
        rows = []
        for a in Asset.search([('wallet_id.partner_id', '=', me.id)]):
            rows.append({'id': a.id, 'name': a.name, 'symbol': a.symbol, 'network': a.network_id.name or '',
                         'quantity': a.quantity, 'valuation': a.valuation or 0.0,
                         'valued_at': fields.Datetime.to_string(a.valued_at)[:16] if a.valued_at else '',
                         'source': a.valuation_source or ''})
        rows.sort(key=lambda r: -r['valuation'])
        return {'rows': rows}

    # ── взаиморасчёты по сделкам ─────────────────────────────────────
    def _settlements(self, me, today, put, overdue):
        Payment = self.env['coop.deal.payment'].sudo()
        rows = []
        totals = {'owed_me': 0.0, 'i_owe': 0.0, 'overdue_me': 0.0, 'overdue_i': 0.0}
        for p in Payment.search(['|', ('payer_id', '=', me.id), ('payee_id', '=', me.id),
                                 ('state', 'in', ('planned', 'overdue'))], order='due_on'):
            to_me = p.payee_id == me
            late = p.state == 'overdue' or (p.due_on and p.due_on < today)
            other = p.payer_id if to_me else p.payee_id
            if to_me:
                totals['owed_me'] += p.amount
            else:
                totals['i_owe'] += p.amount
            if late:
                totals['overdue_me' if to_me else 'overdue_i'] += p.amount
                overdue['in' if to_me else 'out'] += p.amount
                overdue['items'].append({'date': _d(p.due_on), 'what': '%s — %s' % (p.deal_id.number, other.name),
                                         'amount': p.amount, 'sign': 1 if to_me else -1, 'kind': 'deal',
                                         'note': 'мне должны' if to_me else 'я должен'})
            elif p.due_on:
                put(p.due_on, 'contract' if to_me else 'out', p.amount)
            rows.append({'id': p.id, 'deal_id': p.deal_id.id, 'deal': p.deal_id.number,
                         'subject': p.deal_id.name, 'name': p.name or '', 'other': other.name or '',
                         'due_on': _d(p.due_on), 'amount': p.amount, 'to_me': to_me, 'late': late,
                         'days_late': (today - p.due_on).days if late and p.due_on else 0})
        return {'rows': rows, 'totals': totals}

    # ── открытая статистика платформы ────────────────────────────────
    def _platform(self, today):
        """Только сводные числа, без имён и без доходности пулов
        (заключение юриста, раздел Г)."""
        env = self.env
        year_ago = today - timedelta(days=365)
        Account = env['coop.share.account'].sudo()
        Move = env['coop.share.move'].sudo()
        Project = env['coop.project'].sudo()
        Contribution = env['coop.project.contribution'].sudo()
        Claim = env['coop.token.claim'].sudo()
        Payment = env['coop.deal.payment'].sudo()
        Issue = env['coop.cfa.issue'].sudo()
        Pool = env['coop.farm.pool'].sudo()

        funds = sum(Account.search([('state', '!=', 'closed')]).mapped('balance'))
        accruals = sum(Move.search([('kind', '=', 'accrual'), ('state', '=', 'confirmed'),
                                    ('date', '>=', year_ago)]).mapped('amount'))
        running = Project.search_count([('state', '=', 'running')])
        done = Project.search_count([('state', '=', 'done')])
        # Не состоялся — и не собранный к сроку, и отменённый инициатором.
        failed = Project.search_count([('state', 'in', ('failed', 'cancelled'))])
        closed_total = running + done + failed
        failed_money = Contribution.search([('project_id.state', 'in', ('failed', 'cancelled')),
                                            ('kind', '=', 'money')])
        returned = failed_money.filtered(lambda c: c.state == 'returned')
        settled = Claim.search_count([('state', '=', 'settled')])
        defaulted = Claim.search_count([('state', '=', 'defaulted')])
        claims_late = Claim.search_count([('delivery_date', '<', today),
                                          ('state', 'not in', ('settled', 'defaulted', 'cancelled', 'draft'))])
        due = Payment.search([('due_on', '>=', year_ago), ('due_on', '<', today), ('state', '!=', 'cancelled')])
        due_sum = sum(due.mapped('amount'))
        late_sum = sum(due.filtered(lambda p: p.state == 'overdue' or p.state == 'planned').mapped('amount'))
        issued = Issue.search([('state', 'in', ('issued', 'redeemed'))])
        cfa_late = issued.filtered(lambda i: i.state == 'issued' and i.maturity_date and i.maturity_date < today)
        no_collateral = issued.filtered(lambda i: not i.collateral)
        pools = Pool.search([])
        return {
            'as_of': _d(today),
            'items': [
                {'label': 'Паевые фонды кооперативов', 'value': funds, 'unit': 'rub',
                 'note': 'кооперативные выплаты за 12 мес.: %s ₽' % '{:,.0f}'.format(accruals).replace(',', ' ')},
                {'label': 'Проекты: идут / завершены', 'value': '%s / %s' % (running, done), 'unit': 'text',
                 'note': 'не состоялось %s%% сборов' % (round(failed / closed_total * 100) if closed_total else 0)},
                {'label': 'Возвращено денежных вкладов при провале', 'unit': 'pct',
                 'value': round(len(returned) / len(failed_money) * 100) if failed_money else 0,
                 'note': '%s из %s вкладов' % (len(returned), len(failed_money))},
                {'label': 'Поставки по токенам: исполнено / сорвано', 'value': '%s / %s' % (settled, defaulted),
                 'unit': 'text', 'note': 'просрочено сейчас: %s' % claims_late},
                {'label': 'Просрочено в платежах по сделкам', 'unit': 'pct',
                 'value': round(late_sum / due_sum * 100) if due_sum else 0,
                 'note': 'от суммы к оплате за 12 мес.'},
                {'label': 'ЦФА: погашено / просрочено', 'unit': 'text',
                 'value': '%s / %s' % (len(issued.filtered(lambda i: i.state == 'redeemed')), len(cfa_late)),
                 'note': 'без обеспечения: %s%% выпусков' % (round(len(no_collateral) / len(issued) * 100) if issued else 0)},
                {'label': 'Пулы фарминга: работают / возвращены', 'unit': 'text',
                 'value': '%s / %s' % (len(pools.filtered(lambda p: p.state == 'active')),
                                      len(pools.filtered(lambda p: p.state == 'refunded'))),
                 'note': 'идёт сбор: %s' % len(pools.filtered(lambda p: p.state == 'raising'))},
            ],
        }
