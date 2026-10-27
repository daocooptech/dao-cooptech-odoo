# -*- coding: utf-8 -*-
"""Деньги и реквизиты участника.

Вкладка настроек по решению 377 от 22 сентября 2026: валюта приёма,
способы расчёта, налоговый режим.

Налоговый режим держим у участника не из любопытства: от него зависит
цена каждого способа расчёта (разбор бухгалтера от 22 сентября), и без
него подсказка «этот способ обойдётся в 6 %» — угадывание.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Поля вкладки, которые у организации правит держатель «Казначейства».
MONEY_FIELDS = ('coop_payout_currency_id', 'coop_tax_regime', 'coop_settlement_method_ids',
                'coop_fx_resident', 'coop_tax_resident')


def _default_currency(env):
    # Рубль явно, а не валюта компании: поле заполнилось при установке,
    # когда у компании ещё стоял доллар чистого Odoo, и у всех участников
    # платформы — и у ТСН в России — валютой приёма оказался USD.
    return env.ref('base.RUB', raise_if_not_found=False) or env.company.currency_id


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_payout_currency_id = fields.Many2one(
        'res.currency', string='Валюта приёма',
        default=lambda self: _default_currency(self.env),
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

    coop_can_edit_money = fields.Boolean(compute='_compute_coop_can_edit_money')

    @api.depends_context('uid')
    def _compute_coop_can_edit_money(self):
        user = self.env.user
        admin = user.has_group('base.group_system')
        for record in self:
            record.coop_can_edit_money = bool(record.id) and (
                admin or user.coop_has_power('treasury', record))

    def write(self, vals):
        # Деньги организации — держателю «Казначейства»: права на запись
        # карточки у него может не быть (её правит держатель «Страницы»),
        # поэтому после проверки полномочия пишется от имени системы.
        money = {k: vals[k] for k in MONEY_FIELDS if k in vals}
        if money and not self.env.su and not self.env.user.has_group('base.group_system'):
            for record in self:
                if not self.env.user.coop_has_power('treasury', record):
                    raise UserError(_(
                        'Деньги и реквизиты «%s» меняет держатель полномочия '
                        '«Казначейство».') % record.display_name)
            super(ResPartner, self.sudo()).write(money)
            vals = {k: v for k, v in vals.items() if k not in money}
            if not vals:
                return True
        return super().write(vals)

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
