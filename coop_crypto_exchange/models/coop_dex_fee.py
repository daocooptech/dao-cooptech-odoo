# -*- coding: utf-8 -*-
"""Комиссия DEX и её возврат торговавшим по обороту.

Решение 434, п. 6: вместо «комиссий пула в стакане» — личные заявки
участника из его кошелька и комиссия DEX с возвратом торговавшим по
обороту. Решение 436, п. 8: **0,1 % от суммы обмена, возврат 50 %**.

- комиссию платит откликнувшийся (тот, кто забирает заявку из стакана);
- раз в месяц половина собранной за месяц комиссии возвращается всем,
  кто торговал, пропорционально обороту (обе стороны каждого обмена) —
  кооперативная выплата по участию; вторая половина — оператору DEX,
  отдельному юрлицу (решение 435, п. 1);
- считаются только состоявшиеся обмены.

Платформа денег не держит: комиссия и возврат — учёт обязательств
оператора и участников, расчёт идёт их переводами.
"""
from collections import defaultdict
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

FEE_RATE = 0.001      # 0,1 % от суммы обмена
REBATE_SHARE = 0.5    # половина комиссии — назад торговавшим


class CoopCryptoTrade(models.Model):
    _inherit = 'coop.crypto.trade'

    fee = fields.Monetary(string='Комиссия DEX, ₽', compute='_compute_fee', store=True,
                          help='0,1 % от суммы обмена; платит откликнувшийся.')

    @api.depends('total')
    def _compute_fee(self):
        for trade in self:
            trade.fee = round((trade.total or 0) * FEE_RATE, 2)


class CoopDexRebate(models.Model):
    """Возврат комиссии участнику за месяц: его доля в обороте месяца ×
    половина собранной за месяц комиссии."""
    _name = 'coop.dex.rebate'
    _description = 'Возврат комиссии DEX по обороту'
    _order = 'month desc, rebate desc, id'

    month = fields.Char(string='Месяц', required=True, index=True, help='ГГГГ-ММ')
    partner_id = fields.Many2one('res.partner', string='Участник', required=True, index=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.ref('base.RUB'))
    turnover = fields.Monetary(string='Оборот за месяц, ₽')
    share = fields.Float(string='Доля оборота, %', digits=(6, 3))
    fee_paid = fields.Monetary(string='Заплачено комиссии, ₽')
    rebate = fields.Monetary(string='Возврат, ₽')
    state = fields.Selection([('accrued', 'Начислен'), ('paid', 'Выплачен')],
                             string='Состояние', default='accrued', required=True)

    _month_partner_uniq = models.Constraint('unique(month, partner_id)',
                                            'Возврат за месяц у участника один.')

    @api.model
    def _rebate_month(self, month_start):
        """Пересчитать возвраты за месяц. Повторный вызов заменяет
        начисленное за этот месяц — выплаченное не трогает."""
        month_start = month_start.replace(day=1)
        month_end = month_start + relativedelta(months=1)
        key = month_start.strftime('%Y-%m')
        trades = self.env['coop.crypto.trade'].sudo().search([
            ('state', '=', 'done'),
            ('date', '>=', fields.Datetime.to_datetime(month_start)),
            ('date', '<', fields.Datetime.to_datetime(month_end)),
        ])
        if not trades:
            return 0
        turnover = defaultdict(float)
        fees = defaultdict(float)
        for trade in trades:
            turnover[trade.maker_id.id] += trade.total
            turnover[trade.taker_id.id] += trade.total
            fees[trade.taker_id.id] += trade.fee
        pot = sum(trades.mapped('fee')) * REBATE_SHARE
        whole = sum(turnover.values()) or 1.0
        existing = self.sudo().search([('month', '=', key)])
        paid = existing.filtered(lambda r: r.state == 'paid')
        (existing - paid).unlink()
        done = set(paid.mapped('partner_id').ids)
        made = 0
        for partner_id, amount in turnover.items():
            if partner_id in done:
                continue
            self.sudo().create({
                'month': key, 'partner_id': partner_id, 'turnover': amount,
                'share': amount / whole * 100, 'fee_paid': fees.get(partner_id, 0.0),
                'rebate': round(pot * amount / whole, 2),
            })
            made += 1
        return made

    @api.model
    def _cron_monthly(self):
        """Первого числа — возвраты за прошедший месяц."""
        first = date.today().replace(day=1)
        return self._rebate_month(first - relativedelta(months=1))

    @api.model
    def dex_rebate_summary(self):
        """Для экрана биржи: условия и мои возвраты за последние месяцы."""
        me = self.env.user.partner_id
        mine = self.sudo().search([('partner_id', '=', me.id)], limit=12)
        return {
            'fee_pct': FEE_RATE * 100, 'rebate_pct': REBATE_SHARE * 100,
            'rows': [{'month': r.month, 'turnover': r.turnover, 'rebate': r.rebate,
                      'state': r.state} for r in mine],
        }
