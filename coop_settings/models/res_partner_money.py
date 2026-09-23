# -*- coding: utf-8 -*-
"""Деньги и реквизиты участника.

Вкладка настроек по решению 377 от 22 сентября 2026: валюта приёма,
способы расчёта, налоговый режим.

Налоговый режим держим у участника не из любопытства: от него зависит
цена каждого способа расчёта (разбор бухгалтера от 22 сентября), и без
него подсказка «этот способ обойдётся в 6 %» — угадывание.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_payout_currency_id = fields.Many2one(
        'res.currency', string='Валюта приёма',
        default=lambda self: self.env.company.currency_id,
        help='В чём хотите получать. Мультивалютность держится на п. 2 '
             'ст. 317 ГК: цена может быть выражена в чём угодно, платёж '
             'проходит в рублях.')

    coop_tax_regime = fields.Selection([
        ('none', 'Не применимо'),
        ('npd', 'Самозанятость (НПД)'),
        ('usn_income', 'УСН «доходы»'),
        ('usn_profit', 'УСН «доходы минус расходы»'),
        ('patent', 'Патент'),
        ('osno', 'Общая система'),
    ], string='Налоговый режим', default='none', index=True,
        help='От него зависит, во что обойдётся каждый способ расчёта. '
             'Без него платформа не может честно назвать цену.')

    coop_settlement_method_ids = fields.Many2many(
        'coop.settlement.method', 'coop_partner_settlement_rel',
        'partner_id', 'method_id', string='Принимаю расчёт',
        domain="[('status', '!=', 'planned')]",
        help='Чем с вами можно рассчитаться. Рядом с каждым способом '
             'написано, во что он обходится и что нужно, чтобы он '
             'работал.')

    coop_conditional_settlement_ids = fields.Many2many(
        'coop.settlement.method', compute='_compute_other_settlements',
        string='Работает при условии',
        help='Способы, законные не при всяких обстоятельствах: нужен '
             'статус, посредник или определённый вид сделки. Условие '
             'написано рядом.')
    coop_planned_settlement_ids = fields.Many2many(
        'coop.settlement.method', compute='_compute_other_settlements',
        string='Готовится',
        help='Платформа этого ещё не умеет. Пункт стоит, чтобы было '
             'видно, чего ждать.')

    def _compute_other_settlements(self):
        Method = self.env['coop.settlement.method']
        conditional = Method.search([('status', '=', 'conditional')])
        planned = Method.search([('status', '=', 'planned')])
        for record in self:
            record.coop_conditional_settlement_ids = conditional
            record.coop_planned_settlement_ids = planned

    @api.constrains('coop_settlement_method_ids')
    def _check_settlement_ready(self):
        """Нельзя пообещать то, чего платформа ещё не умеет.

        Проверяется только готовность, не законность. Способ «при
        условии» выбрать можно: условие — часть договорённости сторон, и
        решать, выполнимо ли оно, им, а не платформе. А вот способ,
        которого на платформе физически нет, в списке «принимаю расчёт»
        означал бы обещание, которое некому исполнить.
        """
        for record in self:
            planned = record.coop_settlement_method_ids.filtered(
                lambda m: m.status == 'planned')
            if planned:
                raise ValidationError(_(
                    'Платформа этого ещё не умеет: %(what)s. Обещать '
                    'такой расчёт рано.',
                    what=', '.join(planned.mapped('name'))))
