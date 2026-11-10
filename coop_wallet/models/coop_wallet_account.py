# -*- coding: utf-8 -*-
"""Счета участника по странам, банкам и валютам (задача 400, решение 639).

Счёт — не деньги, а запись «где у меня лежит валюта»: страна, банк, вид
(банковский счёт, карта, цифровая валюта ЦБ), валюта. Платформа денег не
держит; здесь учёт того, что человек сам назвал, и подтверждённых
поступлений. Основной счёт — один на валюту.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Цифровые валюты ЦБ, подтверждённые разбором `legal-counsel` 10.11.2026:
# Россия, Индия, Казахстан. США и ЕС не показываем: у них цифрового
# доллара и евро в обращении нет (Казахстан — после чтения закона).
CBDC_CURRENCIES = ('RUB', 'INR', 'KZT')


class CoopWalletAccount(models.Model):
    _name = 'coop.wallet.account'
    _description = 'Счёт участника'
    _order = 'currency_id, sequence, id'
    _rec_name = 'label'

    wallet_id = fields.Many2one(
        'coop.wallet', string='Кошелёк', required=True, index=True,
        ondelete='cascade')
    partner_id = fields.Many2one(
        related='wallet_id.partner_id', store=True, index=True,
        string='Владелец')
    country_id = fields.Many2one('res.country', string='Страна')
    bank = fields.Char(string='Банк')
    kind = fields.Selection([
        ('bank', 'Банковский счёт'),
        ('card', 'Карта'),
        ('cbdc', 'Цифровая валюта ЦБ'),
    ], string='Вид', required=True, default='bank')
    currency_id = fields.Many2one(
        'res.currency', string='Валюта', required=True, index=True,
        domain="[('coop_wallet_enabled', '=', True)]")
    label = fields.Char(
        string='Как показывать', required=True,
        help='«Счёт •• 4412, Сбербанк» или «Цифровой рубль».')
    is_main = fields.Boolean(string='Основной в этой валюте')
    sequence = fields.Integer(string='Порядок', default=10)
    active = fields.Boolean(default=True)
    movement_ids = fields.One2many(
        'coop.wallet.movement', 'account_id', string='Движения')

    @api.constrains('is_main', 'currency_id', 'wallet_id', 'active')
    def _check_single_main(self):
        for record in self.filtered(lambda a: a.is_main and a.active):
            twin = self.search([
                ('id', '!=', record.id), ('wallet_id', '=', record.wallet_id.id),
                ('currency_id', '=', record.currency_id.id),
                ('is_main', '=', True)], limit=1)
            if twin:
                raise ValidationError(_(
                    'Основной счёт в валюте %(cur)s может быть только один: '
                    '«%(label)s».', cur=record.currency_id.name,
                    label=twin.label))

    @api.constrains('kind', 'currency_id')
    def _check_cbdc(self):
        for record in self:
            if record.kind == 'cbdc' and record.currency_id.name not in CBDC_CURRENCIES:
                raise ValidationError(_(
                    'Цифровая валюта ЦБ в валюте %s на платформе не подключена: '
                    'только рубль, рупия и тенге.', record.currency_id.name))
