# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import format_amount

# П. 2 ст. 24 3085-1: кооперативные выплаты «не должны превышать 20
# процентов от доходов потребительского общества».
PAYOUT_LIMIT_SHARE = 0.2


class CoopTaxPayoutLimit(models.Model):
    """Лимит кооперативных выплат за год (решение 517).

    Закон ограничивает выплаты пайщикам 20 % «от доходов», но не говорит,
    что такое доходы: от чего считать — пишет в уставе узел. Бухгалтер
    после закрытия года вносит три числа, платформа считает потолок —
    20 % от выбранной базы, но не больше нераспределённой прибыли после
    фондов (84.30): раздать больше, чем осталось, нельзя ни при какой базе.

    Начисления по итогам года сверяются с потолком при проведении.
    """
    _name = 'coop.tax.payout.limit'
    _description = 'Лимит кооперативных выплат за год'
    _order = 'year desc, cooperative_id'
    _rec_name = 'year'

    cooperative_id = fields.Many2one(
        'res.partner', string='Кооператив', required=True, index=True,
        ondelete='cascade', domain=[('coop_is_cooperative', '=', True)])
    year = fields.Integer(
        string='Год', required=True,
        default=lambda self: fields.Date.context_today(self).year - 1)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id,
        required=True)
    base_kind = fields.Selection([
        ('net_profit', 'Чистая прибыль'),
        ('income_after_taxes', 'Доходы после обязательных платежей'),
    ], string='База', required=True, default='net_profit',
        help='Берётся из устава кооператива при внесении года; правка '
             'устава прошлые годы не пересчитывает.')
    net_profit = fields.Monetary(
        string='Чистая прибыль', currency_field='currency_id',
        help='Предпринимательской части за год (раздельный учёт).')
    income_after_taxes = fields.Monetary(
        string='Доходы после обязательных платежей', currency_field='currency_id',
        help='Доходы предпринимательской части за вычетом налогов и иных '
             'обязательных платежей — буквальное прочтение п. 1 ст. 24 3085-1.')
    retained = fields.Monetary(
        string='Нераспределённая прибыль после фондов', currency_field='currency_id',
        help='Остаток 84.30 после отчислений в фонды по решению собрания.')

    base = fields.Monetary(
        string='База лимита', currency_field='currency_id',
        compute='_compute_limit', store=True)
    limit = fields.Monetary(
        string='Можно начислить', currency_field='currency_id',
        compute='_compute_limit', store=True,
        help='20 % от базы, но не больше нераспределённой прибыли после фондов.')
    accrued = fields.Monetary(
        string='Начислено', currency_field='currency_id', compute='_compute_accrued')
    remaining = fields.Monetary(
        string='Остаток лимита', currency_field='currency_id', compute='_compute_accrued')

    # Делитель распределения (решение 659 п. 2): его видят все члены
    # кооператива — общую сумму и базы, из которых считаются доли. Суммы
    # отдельных членов здесь не хранятся и не показываются.
    distribute_total = fields.Monetary(
        string='К распределению', currency_field='currency_id',
        help='Сколько собрание решило раздать членам по итогам года; '
             'не больше лимита.')
    pct_labor = fields.Float(string='По труду, %', digits=(5, 2))
    pct_turnover = fields.Float(string='По обороту, %', digits=(5, 2))
    pct_share = fields.Float(
        string='По паям, %', digits=(5, 2),
        help='У производственного кооператива (артели) — не больше 50 % '
             '(ст. 12 закона 41-ФЗ).')
    base_labor_hours = fields.Float(
        string='Труд членов за год, ч', digits=(16, 1),
        help='Сумма часов личного трудового участия всех членов.')
    base_turnover = fields.Monetary(
        string='Оборот членов с кооперативом', currency_field='currency_id',
        help='Покупки, услуги и поставки членов через кооператив за год.')
    base_shares = fields.Monetary(
        string='Паи на конец года', currency_field='currency_id',
        compute='_compute_divisor',
        help='Сумма паевых взносов всех членов на 31 декабря.')
    member_count = fields.Integer(string='Членов', compute='_compute_divisor')
    per_hour = fields.Monetary(
        string='На час труда', currency_field='currency_id', compute='_compute_divisor')
    per_turnover_rub = fields.Float(
        string='На рубль оборота', digits=(16, 4), compute='_compute_divisor')
    per_share_rub = fields.Float(
        string='На рубль пая', digits=(16, 4), compute='_compute_divisor')

    _year_unique = models.Constraint(
        'unique(cooperative_id, year)',
        'Лимит за этот год у кооператива уже внесён.',
    )

    @api.onchange('cooperative_id')
    def _onchange_cooperative_id(self):
        if self.cooperative_id:
            self.base_kind = self.cooperative_id.coop_payout_limit_base

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'base_kind' not in vals and vals.get('cooperative_id'):
                vals['base_kind'] = self.env['res.partner'].browse(
                    vals['cooperative_id']).coop_payout_limit_base
        return super().create(vals_list)

    @api.depends('base_kind', 'net_profit', 'income_after_taxes', 'retained')
    def _compute_limit(self):
        for record in self:
            record.base = record.net_profit if record.base_kind == 'net_profit' \
                else record.income_after_taxes
            record.limit = max(0.0, min(PAYOUT_LIMIT_SHARE * record.base, record.retained))

    def _accrual_moves(self):
        self.ensure_one()
        return self.env['coop.share.move'].sudo().search([
            ('kind', '=', 'accrual'), ('state', '=', 'confirmed'),
            ('account_id.cooperative_id', '=', self.cooperative_id.id),
            ('coop_result_year', '=', self.year),
        ])

    def _compute_accrued(self):
        for record in self:
            record.accrued = sum(record._accrual_moves().mapped('amount')) \
                if record.cooperative_id and record.year else 0.0
            record.remaining = record.limit - record.accrued

    @api.depends('cooperative_id', 'year', 'distribute_total', 'pct_labor',
                 'pct_turnover', 'pct_share', 'base_labor_hours', 'base_turnover')
    def _compute_divisor(self):
        Move = self.env['coop.share.move'].sudo()
        for record in self:
            shares, members = 0.0, 0
            if record.cooperative_id and record.year:
                moves = Move.search([
                    ('state', '=', 'confirmed'),
                    ('account_id.cooperative_id', '=', record.cooperative_id.id),
                    ('date', '<=', '%s-12-31' % record.year),
                    ('kind', 'in', ('share', 'extra', 'in_kind', 'return')),
                ])
                # Возврат хранится со знаком минус, как и в балансе счёта.
                shares = sum(moves.mapped('amount'))
                members = self.env['coop.share.account'].sudo().search_count([
                    ('cooperative_id', '=', record.cooperative_id.id),
                    '|', ('joined_on', '=', False),
                    ('joined_on', '<=', '%s-12-31' % record.year)])
            record.base_shares = max(0.0, shares)
            record.member_count = members
            total = record.distribute_total
            record.per_hour = total * record.pct_labor / 100 / record.base_labor_hours \
                if record.base_labor_hours else 0.0
            record.per_turnover_rub = total * record.pct_turnover / 100 / record.base_turnover \
                if record.base_turnover else 0.0
            record.per_share_rub = total * record.pct_share / 100 / record.base_shares \
                if record.base_shares else 0.0

    @api.constrains('distribute_total', 'pct_labor', 'pct_turnover', 'pct_share', 'limit')
    def _check_divisor(self):
        for record in self:
            pcts = (record.pct_labor, record.pct_turnover, record.pct_share)
            if any(p < 0 or p > 100 for p in pcts):
                raise ValidationError(_('Доля базы — от 0 до 100 %.'))
            if record.distribute_total < 0:
                raise ValidationError(_('Сумма к распределению не может быть меньше нуля.'))
            if record.distribute_total > record.limit + 0.005:
                raise ValidationError(_(
                    'К распределению больше лимита года: раздать можно не '
                    'больше %s.') % format_amount(self.env, record.limit, record.currency_id))
            if record.distribute_total and abs(sum(pcts) - 100) > 0.005:
                raise ValidationError(_(
                    'Доли по труду, обороту и паям вместе должны дать 100 %.'))
            if record.cooperative_id.coop_cooperative_kind == 'production' \
                    and record.pct_share > 50 + 0.005:
                raise ValidationError(_(
                    'У производственного кооператива по паям распределяют не '
                    'больше 50 %% прибыли, подлежащей распределению (ст. 12 '
                    'закона 41-ФЗ). Сейчас — %s %%.') % record.pct_share)

    @api.constrains('net_profit', 'income_after_taxes', 'retained')
    def _check_figures(self):
        for record in self:
            if record.retained < 0:
                raise ValidationError(_(
                    'Нераспределённая прибыль после фондов не может быть '
                    'меньше нуля: из убытка кооперативные выплаты не '
                    'начисляют. Поставьте 0.'))

    def action_open_accruals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Начисления по итогам %s года') % self.year,
            'res_model': 'coop.share.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self._accrual_moves().ids)],
        }
