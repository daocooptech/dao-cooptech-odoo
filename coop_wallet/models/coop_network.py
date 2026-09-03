# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CoopWalletNetwork(models.Model):
    """Блокчейн-сеть, подключённая к кошельку.

    Решение владельца: блокчейнов на платформе несколько, участник
    настраивает интеграции в настройках и при записи транзакции выбирает,
    в какую сеть её писать. В макете это сказано ещё определённее:
    кошелёк мультисетевой и некастодиальный, а подключить можно любую
    сеть с открытым RPC — публичную или собственную разработку
    кооператива, — указав адрес узла, идентификатор сети и обозначение
    монеты.

    Отсюда сеть — запись справочника, а не значение перечисления. Иначе
    «подключить свою сеть» означало бы правку кода, и обещание из макета
    оказалось бы невыполнимым.

    Ключей платформа не хранит. Здесь лежит то, что публично: как
    достучаться до сети и как называется её монета.
    """
    _name = 'coop.wallet.network'
    _description = 'Блокчейн-сеть'
    _order = 'sequence, id'

    name = fields.Char(string='Сеть', required=True)
    code = fields.Char(
        string='Код', required=True,
        help='Короткое обозначение для фильтров: btc, eth, ton.')
    symbol = fields.Char(
        string='Монета сети', required=True,
        help='Обозначение основной монеты: BTC, ETH, TON.')
    sequence = fields.Integer(string='Порядок', default=10)

    rpc_url = fields.Char(
        string='Адрес узла (RPC/API)',
        help='Точка, через которую кошелёк говорит с сетью. Для '
             'собственной сети кооператива — её же собственный узел.')
    chain_id = fields.Char(string='Идентификатор сети')
    explorer_url = fields.Char(
        string='Обозреватель',
        help='Куда ведёт ссылка на транзакцию. Без него хэш операции '
             'остаётся строкой, которую некуда проверить.')

    is_custom = fields.Boolean(
        string='Своя сеть',
        help='Сеть, поднятая кооперативом или сообществом, а не публичная. '
             'Подключается ровно так же — по адресу узла.')
    active = fields.Boolean(string='Подключена', default=True)

    _code_uniq = models.Constraint(
        'unique(code)',
        'Сеть с таким кодом уже подключена.',
    )


class CoopWalletAddress(models.Model):
    """Адрес кошелька в конкретной сети.

    У каждой сети свой адрес: один кошелёк — много адресов, по одному на
    сеть. В макете это оговорено прямо, и путать их нельзя: перевод на
    адрес чужой сети означает потерю средств.
    """
    _name = 'coop.wallet.address'
    _description = 'Адрес в сети'
    _order = 'network_id, id'
    _rec_name = 'address'

    wallet_id = fields.Many2one(
        'coop.wallet', string='Кошелёк', required=True, index=True,
        ondelete='cascade')
    network_id = fields.Many2one(
        'coop.wallet.network', string='Сеть', required=True, index=True,
        ondelete='restrict')
    address = fields.Char(string='Адрес', required=True)

    _one_per_network = models.Constraint(
        'unique(wallet_id, network_id)',
        'Адрес в этой сети у кошелька уже есть.',
    )


class CoopWalletAsset(models.Model):
    """Актив на кошельке: сколько чего и в какой сети.

    Один и тот же по названию актив живёт в разных сетях и там это разные
    активы: USDT в Ethereum и USDT в TON нельзя ни сложить, ни перевести
    друг в друга напрямую. Поэтому сеть — часть определения актива, а не
    примечание к нему.
    """
    _name = 'coop.wallet.asset'
    _description = 'Актив кошелька'
    _order = 'valuation desc, id'

    wallet_id = fields.Many2one(
        'coop.wallet', string='Кошелёк', required=True, index=True,
        ondelete='cascade')
    network_id = fields.Many2one(
        'coop.wallet.network', string='Сеть', required=True, index=True,
        ondelete='restrict')
    name = fields.Char(string='Актив', required=True)
    symbol = fields.Char(string='Обозначение', required=True)
    standard = fields.Char(
        string='Стандарт',
        help='ERC-20, TRC-20 и подобные. У монеты самой сети пусто.')

    quantity = fields.Float(
        string='Баланс', digits=(16, 8), required=True, default=0.0,
        help='Количество актива. Дробность до восьми знаков: у части '
             'монет мельче копейки принято считать до сатоши.')
    valuation = fields.Monetary(
        string='Оценка', currency_field='currency_id',
        help='Пересчёт в рубли по курсу. Справочно: курс определяет рынок, '
             'а не платформа.')
    currency_id = fields.Many2one(related='wallet_id.currency_id', store=True)

    # «Эквивалент по текущему курсу» без времени и источника — это не
    # цифра, а обещание. Курс меняется за минуты, и человек вправе знать,
    # на какой момент он смотрит и откуда взят.
    valued_at = fields.Datetime(string='Оценка на')
    valuation_source = fields.Char(
        string='Источник курса',
        help='Биржа или агрегатор, откуда взят курс.')

    balance_at = fields.Datetime(
        string='Остаток получен',
        help='Кошелёк некастодиальный: монеты могли уйти другим '
             'приложением тем же ключом, и наш остаток тогда устарел.')

    _one_per_asset = models.Constraint(
        'unique(wallet_id, network_id, symbol)',
        'Такой актив в этой сети у кошелька уже есть.',
    )


class CoopWalletMethod(models.Model):
    """Привязанный способ оплаты фиатного кошелька.

    Реквизиты не хранятся: только то, по чему человек узнаёт свой способ
    — вид, банк и последние цифры. Полный номер карты в базе узла не
    нужен ни для чего: платежи идут через агрегатора, и он хранит их у
    себя.
    """
    _name = 'coop.wallet.method'
    _description = 'Способ оплаты'
    _order = 'sequence, id'

    wallet_id = fields.Many2one(
        'coop.wallet', string='Кошелёк', required=True, index=True,
        ondelete='cascade')
    kind = fields.Selection([
        ('card', 'Банковская карта'),
        ('sbp', 'Система быстрых платежей'),
        ('account', 'Расчётный счёт'),
    ], string='Вид', required=True, default='card')
    label = fields.Char(
        string='Как показывать', required=True,
        help='«Карта МИР •• 4412 (Сбербанк)» или номер телефона для СБП.')
    sequence = fields.Integer(string='Порядок', default=10)
    is_default = fields.Boolean(string='Основной')

    @api.constrains('is_default')
    def _check_single_default(self):
        for record in self.filtered('is_default'):
            twin = self.search([
                ('id', '!=', record.id),
                ('wallet_id', '=', record.wallet_id.id),
                ('is_default', '=', True),
            ], limit=1)
            if twin:
                raise ValidationError(_(
                    'Основной способ оплаты может быть только один: «%s».'
                ) % twin.label)
