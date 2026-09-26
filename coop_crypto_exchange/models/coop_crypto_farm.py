# -*- coding: utf-8 -*-
"""Фарминг на DEX бирже: пулы ликвидности под настоящие проекты.

Владелец 26.09.2026: «сделай функцию yield farming, чтобы можно было
собирать пул ликвидности под реальные проекты». Токеномика сюда не
входит — там только токены, обеспеченные ресурсами; пулы DEX собирают
цифровую валюту.

Как устроено:

- пул принадлежит проекту платформы и собирает одну монету в одной сети
  (USDT · TON, TON, BTC…) до цели к сроку;
- участник вносит монету и получает долю пула; доход начисляется в той же
  монете по ставке пула, годовых: часть — комиссии со сделок, которые
  пул ведёт в стакане DEX, часть — выплаты проекта из выручки;
- внесённое заперто на срок пула; доход можно забирать в любой момент;
- не собрал к сроку — пул закрывается, каждому возвращается внесённое.

Платформа ключей и средств не держит: пул — учёт долей и обязательств
проекта, монеты ходят между кошельками участников и проекта.
"""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .coop_crypto import ASSETS

FARM_STATES = [
    ('raising', 'Идёт сбор'),
    ('active', 'Работает'),
    ('closed', 'Завершён'),
    ('refunded', 'Не собран — возврат'),
]

RISKS = [
    ('low', 'Низкий'),
    ('medium', 'Средний'),
    ('high', 'Высокий'),
]


def _own_projects(model):
    """Пул открывают под свой идущий проект; администратор — под любой."""
    if model.env.user.has_group('base.group_system'):
        return [('state', 'in', ('gathering', 'running'))]
    return [('partner_id', '=', model.env.user.partner_id.id),
            ('state', 'in', ('gathering', 'running'))]


class CoopFarmPool(models.Model):
    _name = 'coop.farm.pool'
    _description = 'Пул ликвидности под проект'
    _order = 'state_rank, apr desc, id desc'

    name = fields.Char(string='Название', compute='_compute_name', store=True)
    project_id = fields.Many2one('coop.project', string='Проект', required=True,
                                 index=True, ondelete='cascade', domain=_own_projects)
    partner_id = fields.Many2one(related='project_id.partner_id', string='Инициатор',
                                 store=True)
    city = fields.Char(related='project_id.city', store=True)
    asset = fields.Selection(ASSETS, string='Монета', required=True, default='USDT', index=True)
    network_id = fields.Many2one('coop.wallet.network', string='Сеть', required=True,
                                 domain="[('code', '!=', 'koop')]")
    purpose = fields.Char(string='На что пойдёт ликвидность')
    target = fields.Float(string='Цель, монет', digits=(16, 8), required=True)
    min_stake = fields.Float(string='Взнос от, монет', digits=(16, 8))
    apr_fee = fields.Float(string='Комиссии пула, % годовых', digits=(6, 2))
    apr_project = fields.Float(string='Выплаты проекта, % годовых', digits=(6, 2))
    apr = fields.Float(string='Доходность, % годовых', compute='_compute_apr', store=True,
                       digits=(6, 2))
    lock_days = fields.Integer(string='Срок, дней', default=180)
    date_start = fields.Date(string='Сбор начат', default=fields.Date.today)
    date_deadline = fields.Date(string='Собираем до')
    date_end = fields.Date(string='Пул работает до')
    state = fields.Selection(FARM_STATES, string='Состояние', default='raising',
                             required=True, index=True)
    state_rank = fields.Integer(compute='_compute_state_rank', store=True)
    risk = fields.Selection(RISKS, string='Риск', default='medium')
    stake_ids = fields.One2many('coop.farm.stake', 'pool_id', string='Взносы')
    tvl = fields.Float(string='В пуле, монет', compute='_compute_tvl', digits=(16, 8))
    staker_count = fields.Integer(string='Участников', compute='_compute_tvl')
    paid_total = fields.Float(string='Выплачено дохода', compute='_compute_tvl',
                              digits=(16, 8))

    @api.depends('project_id.name', 'asset', 'network_id')
    def _compute_name(self):
        for pool in self:
            coin = pool.asset or ''
            if pool.asset == 'USDT' and pool.network_id:
                coin = 'USDT · %s' % pool.network_id.name
            pool.name = '%s — %s' % (pool.project_id.name or '', coin)

    @api.depends('apr_fee', 'apr_project')
    def _compute_apr(self):
        for pool in self:
            pool.apr = (pool.apr_fee or 0) + (pool.apr_project or 0)

    @api.depends('state')
    def _compute_state_rank(self):
        rank = {'raising': 0, 'active': 1, 'closed': 2, 'refunded': 3}
        for pool in self:
            pool.state_rank = rank.get(pool.state, 9)

    def _compute_tvl(self):
        stakes = self.env['coop.farm.stake'].sudo().search([('pool_id', 'in', self.ids)])
        for pool in self:
            mine = stakes.filtered(lambda s: s.pool_id == pool)
            live = mine.filtered(lambda s: s.state == 'active')
            pool.tvl = sum(live.mapped('amount'))
            pool.staker_count = len(set(live.mapped('partner_id').ids))
            pool.paid_total = sum(mine.mapped('harvested'))

    # ── Экран фарминга ──────────────────────────────────────────────

    def _coin_label(self):
        self.ensure_one()
        return 'USDT · %s' % self.network_id.name if self.asset == 'USDT' else self.asset

    def _rub_price(self):
        """Цена монеты в рублях — последняя сделка пары на DEX, иначе середина стакана."""
        self.ensure_one()
        domain = [('asset', '=', self.asset), ('network_id', '=', self.network_id.id)]
        trade = self.env['coop.crypto.trade'].sudo().search(
            domain + [('state', 'in', ('agreed', 'rub_sent', 'done'))], order='date desc', limit=1)
        if trade:
            return trade.price
        ask, bid = self.env['coop.crypto.offer']._coop_best_prices(domain)
        return ((ask or 0) + (bid or 0)) / (2 if ask and bid else 1) if (ask or bid) else 0.0

    def _row(self, prices):
        self.ensure_one()
        price = prices.get((self.asset, self.network_id.id), 0.0)
        project = self.project_id
        today = fields.Date.context_today(self)
        return {
            'id': self.id,
            'project_id': project.id,
            'project': project.name,
            'summary': project.summary or '',
            'city': project.city or '',
            'initiator': self.partner_id.name or '',
            'coin': self._coin_label(),
            'asset': self.asset,
            'purpose': self.purpose or '',
            'target': self.target, 'tvl': self.tvl,
            'tvl_rub': self.tvl * price, 'price_rub': price,
            'progress': min(100, round(self.tvl / self.target * 100)) if self.target else 0,
            'min_stake': self.min_stake,
            'apr': self.apr, 'apr_fee': self.apr_fee, 'apr_project': self.apr_project,
            'lock_days': self.lock_days,
            'days_left': (self.date_deadline - today).days
            if self.date_deadline and self.state == 'raising' else None,
            'date_end': fields.Date.to_string(self.date_end) if self.date_end else '',
            'state': self.state,
            'state_label': dict(FARM_STATES).get(self.state),
            'risk': self.risk, 'risk_label': dict(RISKS).get(self.risk),
            'stakers': self.staker_count,
            'paid': self.paid_total,
            'readiness': project.readiness or 0,
            'open': self.state == 'raising',
        }

    @api.model
    def farm_overview(self):
        pools = self.sudo().search([])
        prices = {}
        for pool in pools:
            key = (pool.asset, pool.network_id.id)
            if key not in prices:
                prices[key] = pool._rub_price()
        me = self.env.user.partner_id
        stakes = self.env['coop.farm.stake'].sudo().search([('partner_id', '=', me.id)],
                                                           order='date desc')
        rows = [pool._row(prices) for pool in pools]
        mine = []
        for stake in stakes:
            price = prices.get((stake.pool_id.asset, stake.pool_id.network_id.id), 0.0)
            mine.append(stake._row(price))
        live = [r for r in rows if r['state'] in ('raising', 'active')]
        return {
            'pools': rows,
            'mine': mine,
            'totals': {
                'tvl_rub': sum(r['tvl_rub'] for r in live),
                'pools': len(live),
                'stakers': len(set(self.env['coop.farm.stake'].sudo().search(
                    [('state', '=', 'active')]).mapped('partner_id').ids)),
                'paid_rub': sum(r['paid'] * r['price_rub'] for r in rows),
                'my_rub': sum(m['amount_rub'] for m in mine if m['state'] == 'active'),
                'my_pending_rub': sum(m['pending'] * m['price_rub'] for m in mine),
            },
        }

    @api.model
    def farm_stake(self, pool_id, amount):
        pool = self.sudo().browse(int(pool_id)).exists()
        amount = float(amount or 0)
        if not pool:
            raise UserError(_('Пул не найден.'))
        if pool.state != 'raising':
            raise UserError(_('Сбор в этот пул закрыт.'))
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
            pool.write({'state': 'active',
                        'date_end': fields.Date.context_today(self) + timedelta(days=pool.lock_days)})
        return stake.id


class CoopFarmStake(models.Model):
    _name = 'coop.farm.stake'
    _description = 'Взнос в пул ликвидности'
    _order = 'date desc, id desc'

    pool_id = fields.Many2one('coop.farm.pool', string='Пул', required=True, index=True,
                              ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Участник', required=True, index=True,
                                 default=lambda self: self.env.user.partner_id)
    amount = fields.Float(string='Внесено, монет', digits=(16, 8), required=True)
    date = fields.Datetime(string='Внесено', default=fields.Datetime.now, required=True)
    state = fields.Selection([
        ('active', 'В пуле'),
        ('withdrawn', 'Выведено'),
    ], string='Состояние', default='active', required=True, index=True)
    withdrawn_on = fields.Datetime(string='Выведено')
    harvested = fields.Float(string='Забрано дохода', digits=(16, 8))
    tx_hash = fields.Char(string='Хэш перевода')

    def _earned(self):
        """Начислено с момента взноса: ставка пула, простые проценты по дням.
        Пул не собран — дохода нет, возвращается только внесённое."""
        self.ensure_one()
        pool = self.pool_id
        if pool.state == 'refunded':
            return 0.0
        end = self.withdrawn_on or fields.Datetime.now()
        if pool.date_end:
            end = min(end, fields.Datetime.to_datetime(pool.date_end))
        days = max((end - self.date).total_seconds() / 86400, 0)
        return self.amount * (pool.apr or 0) / 100 * days / 365

    def _unlock_date(self):
        self.ensure_one()
        pool = self.pool_id
        if pool.date_end:
            return pool.date_end
        return (self.date + timedelta(days=pool.lock_days)).date()

    def _row(self, price):
        self.ensure_one()
        earned = self._earned()
        pool = self.pool_id
        unlock = self._unlock_date()
        today = fields.Date.context_today(self)
        can_withdraw = self.state == 'active' and (
            pool.state in ('closed', 'refunded') or unlock <= today)
        return {
            'id': self.id, 'pool_id': pool.id, 'project': pool.project_id.name,
            'coin': pool._coin_label(), 'amount': self.amount, 'amount_rub': self.amount * price,
            'price_rub': price, 'apr': pool.apr,
            'date': fields.Datetime.to_string(self.date)[:10],
            'unlock': fields.Date.to_string(unlock), 'state': self.state,
            'pool_state': pool.state, 'pool_state_label': dict(FARM_STATES).get(pool.state),
            'earned': earned, 'harvested': self.harvested,
            'pending': max(earned - self.harvested, 0.0),
            'can_withdraw': can_withdraw,
        }

    def _mine(self, stake_id):
        stake = self.sudo().browse(int(stake_id)).exists()
        if not stake or stake.partner_id != self.env.user.partner_id:
            raise UserError(_('Это не ваш взнос.'))
        return stake

    @api.model
    def farm_harvest(self, stake_id):
        stake = self._mine(stake_id)
        pending = stake._earned() - stake.harvested
        if pending <= 0:
            raise UserError(_('Начисленного дохода пока нет.'))
        stake.harvested = stake._earned()
        return pending

    @api.model
    def farm_withdraw(self, stake_id):
        stake = self._mine(stake_id)
        if not stake._row(0)['can_withdraw']:
            raise UserError(_('Срок пула ещё не вышел — внесённое можно забрать с %(date)s.',
                              date=fields.Date.to_string(stake._unlock_date())))
        earned = stake._earned()
        stake.write({'harvested': max(stake.harvested, earned),
                     'state': 'withdrawn', 'withdrawn_on': fields.Datetime.now()})
        return stake.amount
