# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    """Кошелёк TON участника.

    Хранится адрес и только адрес. Ключей у платформы нет и не будет:
    транзакции подписывает кошелёк участника через TON Connect, а мы лишь
    готовим для него параметры. Держать чужие ключи — значит распоряжаться
    чужим имуществом, а это совсем другая деятельность с совсем другими
    требованиями.

    Адрес хранится в том виде, в каком его прислал кошелёк, и проверяется
    на разбираемость: строка, не являющаяся адресом TON, попав в базу,
    всплывёт потом транзакцией в никуда.
    """
    _inherit = 'res.partner'

    coop_ton_address = fields.Char(
        string='Кошелёк TON', copy=False, index=True,
        help='Адрес кошелька в сети TON. Подключается участником через '
             'TON Connect; платформа ключей не хранит и подписать за него '
             'ничего не может.')
    coop_ton_connected_on = fields.Datetime(
        string='Кошелёк подключён', readonly=True, copy=False)
    coop_ton_network = fields.Selection([
        ('testnet', 'Тестовая сеть'),
        ('mainnet', 'Основная сеть'),
    ], string='Сеть кошелька', copy=False)

    coop_claim_ids = fields.One2many(
        'coop.token.claim', 'issuer_id', string='Выпуски токенов')
    coop_holding_ids = fields.One2many(
        'coop.token.holding', 'partner_id', string='Токены на руках')

    @api.constrains('coop_ton_address')
    def _check_ton_address(self):
        """Адрес должен разбираться библиотекой сети, а не «выглядеть похоже».

        Проверка мягкая к отсутствию библиотеки: на стенде без неё модуль
        всё равно должен ставиться, просто без этой проверки. Ронять
        установку из-за необязательной зависимости — плохой обмен.
        """
        try:
            from pytoniq_core import Address
        except ImportError:
            return
        for record in self:
            if not record.coop_ton_address:
                continue
            try:
                Address(record.coop_ton_address)
            except Exception:
                raise ValidationError(_(
                    'Это не адрес TON. Подключайте кошелёк кнопкой, а не '
                    'вписывайте адрес руками: опечатка в адресе — это '
                    'токены, ушедшие в никуда.'))

    def action_disconnect_ton(self):
        """Отвязать кошелёк.

        Токены остаются в кошельке участника: они там и лежали. Платформа
        лишь перестаёт знать адрес — и перестаёт показывать его балансы.
        """
        self.write({
            'coop_ton_address': False,
            'coop_ton_connected_on': False,
            'coop_ton_network': False,
        })
        return True
