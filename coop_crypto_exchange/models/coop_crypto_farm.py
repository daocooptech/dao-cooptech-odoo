# -*- coding: utf-8 -*-
"""Пулы проектов: сбор под настоящий проект с долей выручки и потолком.

Владелец 26.09.2026: «сделай функцию yield farming, чтобы можно было
собирать пул ликвидности под реальные проекты». Переделано по решениям
434–436 (28.09.2026) после заключений юриста и экономиста:

- пул — сбор под проект, а не вклад под процент: проект отдаёт участникам
  **долю своей выручки** (`revenue_share`, %), пока каждый не получит
  **потолок** — `cap_multiple` × внесённого («% выручки + кратность»,
  решение 436, п. 4). «Доходности» и «% годовых» нет нигде (434, п. 4);
- два вида (435, п. 2): **в монете** — сбор и выплаты в монете сбора
  (434, п. 3), до 30.06.2027; **в рублях** — через ЦФА, выпуск нашего
  оператора, на боевой — **учебный**: «демонстрация, не цифровой
  финансовый актив, прав не порождает» (435, п. 3). Долговой ЦФА
  оплачивается только деньгами (ст. 6 282-ФЗ), поэтому рублёвый сбор —
  отдельный вид, а не монета с пометкой;
- участнику начисляется **только записанное и подтверждённое** (434,
  п. 5): инициатор записывает выплату — выручку за период и хэш перевода,
  каждый участник отмечает «получил» или открывает спор; молчание 14 дней
  — получено (436, п. 6). В сборе и до первой выплаты — ноль;
- выплаты идут по графику раз в `payout_days`. Опоздание — «просрочка N
  дней» у пула и проекта и отметка у инициатора; 180 дней без выплат —
  «невозврат», новые пулы инициатору закрыты (436, п. 7);
- открывает пул только инициатор проекта — администратор за него не
  открывает (434, п. 7); сбор под замороженный проект запрещён (434, п. 8).

Платформа ключей и средств не держит: пул — учёт долей и обязательств
проекта, монеты и рубли ходят между участниками и проектом.
"""
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .coop_crypto import ASSETS

POOL_KINDS = [
    ('coin', 'В монете'),
    ('rub', 'В рублях — ЦФА'),
]

FARM_STATES = [
    ('raising', 'Идёт сбор'),
    ('active', 'Идут выплаты'),
    ('closed', 'Завершён'),
    ('default', 'Невозврат'),
    ('refunded', 'Не собран — возврат'),
]

RISKS = [
    ('low', 'Низкий'),
    ('medium', 'Средний'),
    ('high', 'Высокий'),
]

# Молчание участника столько дней — выплата считается полученной (436, п. 6).
CONFIRM_DAYS = 14
# Столько дней без выплат по графику — невозврат (436, п. 7).
DEFAULT_DAYS = 180

# Пометка «учебный выпуск» снята (решение 443): платформа — демо, разделы
# работают так, будто разрешения и лицензии есть. Поле `training` и ключ
# `training_note` остаются в ответе экрана пустыми.
TRAINING_NOTE = ''


def _own_projects(model):
    """Пул открывают только под свой проект в сборе или в работе — и
    администратор тоже только под свой (решение 434, п. 7)."""
    return [('partner_id', 'in', model.env.user.coop_treasury_partner_ids.ids
             or [model.env.user.partner_id.id]),
            ('state', 'in', ('gathering', 'running'))]


class CoopFarmPool(models.Model):
    _name = 'coop.farm.pool'
    _description = 'Пул проекта'
    _order = 'state_rank, id desc'

    name = fields.Char(string='Название', compute='_compute_name', store=True)
    kind = fields.Selection(POOL_KINDS, string='Вид', default='coin', required=True, index=True)
    project_id = fields.Many2one('coop.project', string='Проект', required=True,
                                 index=True, ondelete='cascade', domain=_own_projects)
    partner_id = fields.Many2one(related='project_id.partner_id', string='Инициатор',
                                 store=True, index=True)
    city = fields.Char(related='project_id.city', store=True)
    asset = fields.Selection(ASSETS, string='Монета', index=True)
    network_id = fields.Many2one('coop.wallet.network', string='Сеть',
                                 domain="[('code', '!=', 'koop')]")
    purpose = fields.Char(string='На что пойдёт сбор')
    target = fields.Float(string='Цель', digits=(16, 8), required=True,
                          help='В монете сбора; у рублёвого пула — в рублях.')
    min_stake = fields.Float(string='Взнос от', digits=(16, 8))
    revenue_share = fields.Float(
        string='Доля выручки, %', digits=(6, 2), default=5.0,
        help='Какую часть выручки проект отдаёт участникам пула, пока не выплатит потолок.')
    cap_multiple = fields.Float(
        string='Потолок, × внесённого', digits=(4, 2), default=1.3,
        help='Сколько всего получит участник на каждую внесённую единицу. '
             'Выплачено до потолка — пул завершён.')
    payout_days = fields.Integer(string='Выплаты раз в, дней', default=30)
    lock_days = fields.Integer(string='Срок выплат, дней', default=365,
                               help='Не дошли до потолка за срок — пул завершается с тем, что выплачено.')
    date_start = fields.Date(string='Сбор начат', default=fields.Date.today)
    date_deadline = fields.Date(string='Собираем до')
    date_activated = fields.Date(string='Собран', readonly=True)
    date_end = fields.Date(string='Выплаты до')
    date_default = fields.Date(string='Признан невозвратом', readonly=True)
    state = fields.Selection(FARM_STATES, string='Состояние', default='raising',
                             required=True, index=True)
    state_rank = fields.Integer(compute='_compute_state_rank', store=True)
    risk = fields.Selection(RISKS, string='Риск', default='medium')
    stake_ids = fields.One2many('coop.farm.stake', 'pool_id', string='Взносы')
    payout_ids = fields.One2many('coop.farm.payout', 'pool_id', string='Выплаты')
    tvl = fields.Float(string='Собрано', compute='_compute_tvl', digits=(16, 8))
    staker_count = fields.Integer(string='Участников', compute='_compute_tvl')
    paid_total = fields.Float(string='Выплачено', compute='_compute_tvl', digits=(16, 8))

    # ── вычисляемое ─────────────────────────────────────────────────

    @api.depends('project_id.name', 'asset', 'network_id', 'kind')
    def _compute_name(self):
        for pool in self:
            pool.name = '%s — %s' % (pool.project_id.name or '', pool._coin_label())

    @api.depends('state')
    def _compute_state_rank(self):
        rank = {'raising': 0, 'active': 1, 'default': 2, 'closed': 3, 'refunded': 4}
        for pool in self:
            pool.state_rank = rank.get(pool.state, 9)

    def _compute_tvl(self):
        stakes = self.env['coop.farm.stake'].sudo().search([('pool_id', 'in', self.ids)])
        payouts = self.env['coop.farm.payout'].sudo().search([('pool_id', 'in', self.ids)])
        for pool in self:
            mine = stakes.filtered(lambda s: s.pool_id == pool and s.state == 'active')
            pool.tvl = sum(mine.mapped('amount'))
            pool.staker_count = len(set(mine.mapped('partner_id').ids))
            pool.paid_total = sum(payouts.filtered(lambda p: p.pool_id == pool).mapped('amount'))

    @api.constrains('kind', 'asset', 'network_id')
    def _check_coin(self):
        for pool in self:
            if pool.kind == 'coin' and not (pool.asset and pool.network_id):
                raise ValidationError(_('У пула в монете нужны монета и сеть.'))

    @api.constrains('revenue_share', 'cap_multiple', 'payout_days')
    def _check_terms(self):
        for pool in self:
            if not 0 < pool.revenue_share <= 100:
                raise ValidationError(_('Доля выручки — от 0 до 100 %.'))
            if pool.cap_multiple < 1:
                raise ValidationError(_('Потолок не меньше внесённого (1×).'))
            if pool.payout_days <= 0:
                raise ValidationError(_('Укажите, раз в сколько дней идут выплаты.'))

    # ── открытие: только своё и не под замороженный ─────────────────

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('coop_farm_loader'):
            mine = self.env.user.coop_treasury_partner_ids | self.env.user.partner_id
            for vals in vals_list:
                project = self.env['coop.project'].sudo().browse(vals.get('project_id'))
                if project.partner_id not in mine:
                    raise UserError(_('Пул открывает только инициатор проекта — за другого его '
                                      'не открывает никто, и администратор тоже.'))
                self._check_project_open(project)
                if self.sudo().search_count([('partner_id', '=', project.partner_id.id),
                                             ('state', '=', 'default')]):
                    raise UserError(_('У инициатора есть пул в невозврате — новые пулы ему '
                                      'закрыты, пока долг не погашен.'))
        return super().create(vals_list)

    @api.model
    def _check_project_open(self, project):
        if project.state == 'frozen':
            raise UserError(_('Проект «%(name)s» заморожен — сбор под него запрещён.',
                              name=project.name))
        if project.state not in ('gathering', 'running'):
            raise UserError(_('Пул открывают под проект в сборе или в работе.'))

    # ── подписи и цены ──────────────────────────────────────────────

    def _coin_label(self):
        self.ensure_one()
        if self.kind == 'rub':
            return '₽'
        if self.asset == 'USDT' and self.network_id:
            return 'USDT · %s' % self.network_id.name
        return self.asset or ''

    def _rub_price(self):
        """Цена единицы в рублях: у рублёвого — 1; у монеты — последняя
        сделка пары на DEX, иначе середина стакана. Только справочно."""
        self.ensure_one()
        if self.kind == 'rub':
            return 1.0
        domain = [('asset', '=', self.asset), ('network_id', '=', self.network_id.id)]
        trade = self.env['coop.crypto.trade'].sudo().search(
            domain + [('state', 'in', ('agreed', 'rub_sent', 'done'))], order='date desc', limit=1)
        if trade:
            return trade.price
        ask, bid = self.env['coop.crypto.offer']._coop_best_prices(domain)
        return ((ask or 0) + (bid or 0)) / (2 if ask and bid else 1) if (ask or bid) else 0.0

    # ── график и просрочка ──────────────────────────────────────────

    def _next_due(self):
        """Дата следующей выплаты по графику: от даты сбора шагами
        `payout_days`, первая ещё не закрытая выплатой."""
        self.ensure_one()
        if self.state != 'active' or not self.date_activated:
            return None
        paid = len(self.payout_ids)
        return self.date_activated + timedelta(days=self.payout_days * (paid + 1))

    def _overdue_days(self, today=None):
        self.ensure_one()
        due = self._next_due()
        today = today or fields.Date.context_today(self)
        if not due or due >= today:
            return 0
        return (today - due).days

    def _cap_amount(self):
        self.ensure_one()
        return self.tvl * (self.cap_multiple or 1)

    # ── экран ───────────────────────────────────────────────────────

    def _row(self, prices):
        self.ensure_one()
        price = prices.get(self.id, 0.0)
        project = self.project_id
        today = fields.Date.context_today(self)
        cap = self._cap_amount()
        overdue = self._overdue_days(today)
        me = self.env.user.coop_treasury_partner_ids | self.env.user.partner_id
        return {
            'id': self.id,
            'kind': self.kind,
            'project_id': project.id,
            'project': project.name,
            'summary': project.summary or '',
            'city': project.city or '',
            'initiator': self.partner_id.name or '',
            'coin': self._coin_label(),
            'asset': self.asset or 'RUB',
            'purpose': self.purpose or '',
            'target': self.target, 'tvl': self.tvl,
            'tvl_rub': self.tvl * price, 'price_rub': price,
            'progress': min(100, round(self.tvl / self.target * 100)) if self.target else 0,
            'min_stake': self.min_stake,
            'revenue_share': self.revenue_share, 'cap_multiple': self.cap_multiple,
            'payout_days': self.payout_days,
            'cap': cap, 'paid': self.paid_total,
            'paid_pct': min(100, round(self.paid_total / cap * 100)) if cap else 0,
            'lock_days': self.lock_days,
            'days_left': (self.date_deadline - today).days
            if self.date_deadline and self.state == 'raising' else None,
            'date_end': fields.Date.to_string(self.date_end) if self.date_end else '',
            'next_due': fields.Date.to_string(self._next_due()) if self._next_due() else '',
            'overdue': overdue,
            'payouts': len(self.payout_ids),
            'state': self.state,
            'state_label': dict(FARM_STATES).get(self.state),
            'risk': self.risk, 'risk_label': dict(RISKS).get(self.risk),
            'stakers': self.staker_count,
            'readiness': project.readiness or 0,
            'open': self.state == 'raising' and project.state != 'frozen',
            'frozen': project.state == 'frozen',
            'is_initiator': self.partner_id in me,
            'training': self.kind == 'rub',
        }

    @api.model
    def farm_overview(self):
        pools = self.sudo().search([])
        prices = {}
        by_pair = {}
        for pool in pools:
            key = ('rub',) if pool.kind == 'rub' else (pool.asset, pool.network_id.id)
            if key not in by_pair:
                by_pair[key] = pool._rub_price()
            prices[pool.id] = by_pair[key]
        me = self.env.user.coop_treasury_partner_ids | self.env.user.partner_id
        stakes = self.env['coop.farm.stake'].sudo().search([('partner_id', 'in', me.ids)],
                                                           order='date desc')
        rows = [pool._row(prices) for pool in pools]
        mine = [stake._row() for stake in stakes]
        # Сводка без рублей (434, п. 4): считаем пулы и людей, а не деньги —
        # отдельно по виду, чтобы цифры сходились с вкладкой.
        stakers = self.env['coop.farm.stake'].sudo().search([('state', '=', 'active')])
        totals = {}
        for kind, _label in POOL_KINDS:
            of_kind = [r for r in rows if r['kind'] == kind]
            totals[kind] = {
                'raising': len([r for r in of_kind if r['state'] == 'raising']),
                'active': len([r for r in of_kind if r['state'] == 'active']),
                'overdue': len([r for r in of_kind if r['overdue']]),
                'default': len([r for r in of_kind if r['state'] == 'default']),
                'stakers': len(set(stakers.filtered(lambda s, k=kind: s.pool_id.kind == k)
                                   .mapped('partner_id').ids)),
                'my_awaiting': len([m for m in mine if m['kind'] == kind and m['awaiting'] > 0]),
            }
        return {
            'pools': rows,
            'mine': mine,
            'training_note': TRAINING_NOTE,
            'totals': totals,
        }

    @api.model
    def farm_stake(self, pool_id, amount):
        pool = self.sudo().browse(int(pool_id)).exists()
        amount = float(amount or 0)
        if not pool:
            raise UserError(_('Пул не найден.'))
        if pool.state != 'raising':
            raise UserError(_('Сбор в этот пул закрыт.'))
        self._check_project_open(pool.project_id)
        if amount <= 0:
            raise UserError(_('Укажите, сколько вносите.'))
        if pool.min_stake and amount < pool.min_stake:
            raise UserError(_('Взнос в этот пул — от %(min)s %(coin)s.',
                              min=pool.min_stake, coin=pool._coin_label()))
        left = pool.target - pool.tvl
        if amount > left + 1e-9:
            raise UserError(_('До цели осталось %(left)s %(coin)s — больше внести нельзя.',
                              left=round(left, 8), coin=pool._coin_label()))
        stake = self.env['coop.farm.stake'].sudo().create({
            'pool_id': pool.id, 'partner_id': self.env.user.partner_id.id, 'amount': amount,
        })
        if pool.tvl >= pool.target - 1e-9:
            pool._activate(fields.Date.context_today(self))
        return stake.id

    def _activate(self, when):
        for pool in self:
            pool.write({'state': 'active', 'date_activated': when,
                        'date_end': when + timedelta(days=pool.lock_days)})

    @api.model
    def farm_record_payout(self, pool_id, revenue, tx_hash='', period_start=False, period_end=False):
        """Инициатор записывает выплату: выручку за период и перевод.
        Сумма — доля выручки, но не больше остатка до потолка; делится
        между участниками пропорционально взносам."""
        pool = self.sudo().browse(int(pool_id)).exists()
        me = self.env.user.coop_treasury_partner_ids | self.env.user.partner_id
        if not pool or pool.partner_id not in me:
            raise UserError(_('Выплату по пулу записывает инициатор проекта.'))
        if pool.state not in ('active', 'default'):
            raise UserError(_('Выплаты записывают, когда пул собран.'))
        revenue = float(revenue or 0)
        if revenue <= 0:
            raise UserError(_('Укажите выручку за период.'))
        today = fields.Date.context_today(self)
        payout = pool._make_payout(revenue, today, tx_hash or '',
                                   fields.Date.to_date(period_start) if period_start else None,
                                   fields.Date.to_date(period_end) if period_end else today)
        return payout.id

    def _make_payout(self, revenue, when, tx_hash, period_start=None, period_end=None,
                     line_state=None):
        self.ensure_one()
        # Суммы пула не хранятся и в одном окружении кэшируются: без сброса
        # вторая выплата подряд (загрузчик, повторное нажатие) видит
        # «выплачено» до первой и перескакивает потолок.
        self.invalidate_recordset(['tvl', 'paid_total', 'payout_ids', 'stake_ids'])
        left = max(self._cap_amount() - self.paid_total, 0.0)
        amount = min(revenue * self.revenue_share / 100, left)
        if amount <= 0:
            raise UserError(_('Потолок пула уже выплачен.'))
        last = self.payout_ids.sorted('date')[-1:] if self.payout_ids else self.browse()
        start = period_start or (last.period_end if last else self.date_activated) or when
        payout = self.env['coop.farm.payout'].sudo().create({
            'pool_id': self.id, 'date': when, 'revenue': revenue, 'amount': amount,
            'period_start': start, 'period_end': period_end or when, 'tx_hash': tx_hash,
        })
        live = self.stake_ids.filtered(lambda s: s.state == 'active')
        total = sum(live.mapped('amount')) or 1.0
        for stake in live:
            self.env['coop.farm.payout.line'].sudo().create({
                'payout_id': payout.id, 'stake_id': stake.id,
                'amount': amount * stake.amount / total,
                'state': line_state or 'pending',
            })
        if self.state == 'default':
            self.write({'state': 'active', 'date_default': False})
        self.invalidate_recordset(['paid_total', 'payout_ids'])
        if self.paid_total >= self._cap_amount() - 1e-9:
            self.state = 'closed'
        return payout

    # ── ежедневный обход ────────────────────────────────────────────

    @api.model
    def _cron_daily(self):
        """Молчание 14 дней — выплата получена; несобранное к сроку —
        возврат; истёк срок или выплачен потолок — завершён; 180 дней
        без выплат — невозврат."""
        today = fields.Date.context_today(self)
        Line = self.env['coop.farm.payout.line'].sudo()
        Line.search([('state', '=', 'pending'),
                     ('payout_id.date', '<=', today - timedelta(days=CONFIRM_DAYS))]
                    ).write({'state': 'auto', 'confirmed_on': today})
        pools = self.sudo().search([('state', 'in', ('raising', 'active'))])
        for pool in pools:
            if pool.state == 'raising':
                if pool.date_deadline and pool.date_deadline < today and pool.tvl < pool.target:
                    pool.state = 'refunded'
                continue
            if pool.paid_total >= pool._cap_amount() - 1e-9 or (pool.date_end and pool.date_end < today):
                pool.state = 'closed'
            elif pool._overdue_days(today) >= DEFAULT_DAYS:
                pool.write({'state': 'default', 'date_default': today})
        return True


class CoopFarmStake(models.Model):
    _name = 'coop.farm.stake'
    _description = 'Взнос в пул проекта'
    _order = 'date desc, id desc'

    pool_id = fields.Many2one('coop.farm.pool', string='Пул', required=True, index=True,
                              ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Участник', required=True, index=True,
                                 default=lambda self: self.env.user.partner_id)
    amount = fields.Float(string='Внесено', digits=(16, 8), required=True)
    date = fields.Datetime(string='Внесено', default=fields.Datetime.now, required=True)
    state = fields.Selection([
        ('active', 'В пуле'),
        ('withdrawn', 'Возвращено'),
    ], string='Состояние', default='active', required=True, index=True)
    withdrawn_on = fields.Datetime(string='Возвращено')
    tx_hash = fields.Char(string='Хэш перевода')
    line_ids = fields.One2many('coop.farm.payout.line', 'stake_id', string='Выплаты')

    def _received(self):
        """Получено — только подтверждённое участником или по молчанию."""
        self.ensure_one()
        return sum(self.line_ids.filtered(lambda l: l.state in ('confirmed', 'auto')).mapped('amount'))

    def _awaiting(self):
        self.ensure_one()
        return sum(self.line_ids.filtered(lambda l: l.state == 'pending').mapped('amount'))

    def _row(self):
        self.ensure_one()
        pool = self.pool_id
        pending = self.line_ids.filtered(lambda l: l.state == 'pending').sorted('id')
        return {
            'id': self.id, 'pool_id': pool.id, 'project': pool.project_id.name,
            'kind': pool.kind, 'coin': pool._coin_label(), 'amount': self.amount,
            'cap': self.amount * (pool.cap_multiple or 1),
            'received': self._received(), 'awaiting': self._awaiting(),
            'disputed': sum(self.line_ids.filtered(lambda l: l.state == 'disputed').mapped('amount')),
            'pending_lines': [{'id': l.id, 'amount': l.amount,
                               'date': fields.Date.to_string(l.payout_id.date),
                               'tx_hash': l.payout_id.tx_hash or ''} for l in pending],
            'date': fields.Datetime.to_string(self.date)[:10],
            'state': self.state,
            'pool_state': pool.state, 'pool_state_label': dict(FARM_STATES).get(pool.state),
            'overdue': pool._overdue_days(),
            'can_withdraw': self.state == 'active' and pool.state == 'refunded',
        }

    def _mine(self, stake_id):
        stake = self.sudo().browse(int(stake_id)).exists()
        me = self.env.user.coop_treasury_partner_ids | self.env.user.partner_id
        if not stake or stake.partner_id not in me:
            raise UserError(_('Это не ваш взнос.'))
        return stake

    @api.model
    def farm_withdraw(self, stake_id):
        """Возврат внесённого — только из несобранного пула. У собранного
        внесённое возвращается выплатами из выручки до потолка."""
        stake = self._mine(stake_id)
        if stake.pool_id.state != 'refunded':
            raise UserError(_('Внесённое возвращается выплатами проекта; вернуть взнос целиком '
                              'можно только из несобранного пула.'))
        stake.write({'state': 'withdrawn', 'withdrawn_on': fields.Datetime.now()})
        return stake.amount


class CoopFarmPayout(models.Model):
    """Выплата проекта по пулу за период: доля выручки, делится между
    участниками пропорционально взносам."""
    _name = 'coop.farm.payout'
    _description = 'Выплата по пулу проекта'
    _order = 'date desc, id desc'

    pool_id = fields.Many2one('coop.farm.pool', string='Пул', required=True, index=True,
                              ondelete='cascade')
    date = fields.Date(string='Выплачено', required=True, default=fields.Date.today)
    period_start = fields.Date(string='Выручка с')
    period_end = fields.Date(string='Выручка по')
    revenue = fields.Float(string='Выручка за период', digits=(16, 8))
    amount = fields.Float(string='Выплачено участникам', digits=(16, 8), required=True)
    tx_hash = fields.Char(string='Хэш перевода')
    line_ids = fields.One2many('coop.farm.payout.line', 'payout_id', string='Участникам')


class CoopFarmPayoutLine(models.Model):
    """Доля одного участника в выплате и его подтверждение."""
    _name = 'coop.farm.payout.line'
    _description = 'Выплата участнику пула'
    _order = 'id desc'

    payout_id = fields.Many2one('coop.farm.payout', string='Выплата', required=True, index=True,
                                ondelete='cascade')
    stake_id = fields.Many2one('coop.farm.stake', string='Взнос', required=True, index=True,
                               ondelete='cascade')
    partner_id = fields.Many2one(related='stake_id.partner_id', store=True, index=True)
    amount = fields.Float(string='Сумма', digits=(16, 8), required=True)
    state = fields.Selection([
        ('pending', 'Ждёт подтверждения'),
        ('confirmed', 'Получено'),
        ('auto', 'Получено (без ответа 14 дней)'),
        ('disputed', 'Спор'),
    ], string='Состояние', default='pending', required=True, index=True)
    confirmed_on = fields.Date(string='Подтверждено')
    dispute_note = fields.Char(string='Что не так')

    def _mine(self, line_id):
        line = self.sudo().browse(int(line_id)).exists()
        me = self.env.user.coop_treasury_partner_ids | self.env.user.partner_id
        if not line or line.partner_id not in me:
            raise UserError(_('Это не ваша выплата.'))
        if line.state != 'pending':
            raise UserError(_('По этой выплате уже есть ответ.'))
        return line

    @api.model
    def farm_confirm(self, line_id):
        line = self._mine(line_id)
        line.write({'state': 'confirmed', 'confirmed_on': fields.Date.context_today(self)})
        return True

    @api.model
    def farm_dispute(self, line_id, note=''):
        line = self._mine(line_id)
        line.write({'state': 'disputed', 'dispute_note': (note or '')[:250]})
        return True


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_pool_overdue = fields.Integer(
        string='Пулы с просрочкой', compute='_compute_coop_pool_marks',
        help='Пулы проектов инициатора, где выплата опаздывает по графику.')
    coop_pool_default = fields.Integer(
        string='Пулы в невозврате', compute='_compute_coop_pool_marks')

    def _compute_coop_pool_marks(self):
        Pool = self.env['coop.farm.pool'].sudo()
        today = date.today()
        for partner in self:
            pools = Pool.search([('partner_id', '=', partner.id),
                                 ('state', 'in', ('active', 'default'))])
            partner.coop_pool_default = len(pools.filtered(lambda p: p.state == 'default'))
            partner.coop_pool_overdue = len(pools.filtered(
                lambda p: p.state == 'active' and p._overdue_days(today) > 0))
