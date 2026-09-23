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
        domain="[('status', '!=', 'denied')]",
        help='Чем с вами можно рассчитаться. Рядом с каждым способом '
             'написано, во что он обходится сторонам.')

    coop_denied_settlement_ids = fields.Many2many(
        'coop.settlement.method', compute='_compute_denied_settlements',
        string='Чего нет и не будет',
        help='Запрещённые способы показываются отдельно, с нормой. Через '
             'год кто-нибудь спросит, почему способа нет, и ответ должен '
             'лежать рядом с вопросом, а не в переписке.')

    def _compute_denied_settlements(self):
        denied = self.env['coop.settlement.method'].search(
            [('status', '=', 'denied')])
        for record in self:
            record.coop_denied_settlement_ids = denied

    @api.constrains('coop_settlement_method_ids')
    def _check_settlement_allowed(self):
        """Запрещённый способ нельзя выбрать даже вручную.

        Отбор в поле сужает список, но записи приходят и из загрузчиков,
        и из переноса. Решение 387 разделяет дорогое и запрещённое:
        дорогое показываем с ценой, запрещённого нет ни с какой ценой.
        """
        for record in self:
            denied = record.coop_settlement_method_ids.filtered(
                lambda m: m.status == 'denied')
            if denied:
                raise ValidationError(_(
                    'Так рассчитываться нельзя: %(what)s. %(why)s',
                    what=', '.join(denied.mapped('name')),
                    why=denied[0].deny_reason or ''))
