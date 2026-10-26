# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

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
