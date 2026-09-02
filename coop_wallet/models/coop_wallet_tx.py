# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopWalletTx(models.Model):
    """Операция в блокчейн-сети.

    Отдельно от движений фиатного кошелька, и не для порядка: у сетевой
    операции есть то, чего у рублёвой нет и быть не может — сеть, актив,
    хэш и подтверждение сетью. И наоборот: способа оплаты и сделки у неё
    обычно нет.

    Обмен — одна операция с двумя ногами в разных активах, а иногда и
    сетях. Записывать его двумя несвязанными строками нельзя: по истории
    потом не восстановить, что это был один акт, и человек увидит
    «списание» и «зачисление», между которыми, по его данным, нет связи.
    Поэтому у обмена вторая нога — своё поле.

    Платформа операцию не совершает: ключи у участника, подпись у него
    же. Здесь она отражается и отсюда ведёт ссылка в обозреватель сети,
    где её можно проверить не на слово.
    """
    _name = 'coop.wallet.tx'
    _description = 'Операция в сети'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    wallet_id = fields.Many2one(
        'coop.wallet', string='Кошелёк', required=True, index=True,
        ondelete='cascade')
    partner_id = fields.Many2one(
        related='wallet_id.partner_id', store=True, index=True, string='Владелец')
    network_id = fields.Many2one(
        'coop.wallet.network', string='Сеть', required=True, index=True,
        ondelete='restrict')

    date = fields.Datetime(
        string='Время', required=True, default=fields.Datetime.now, index=True)
    kind = fields.Selection([
        ('in', 'Получение'),
        ('out', 'Отправка'),
        ('swap', 'Обмен'),
        ('fee', 'Комиссия сети'),
    ], string='Операция', required=True, default='in', index=True)

    symbol = fields.Char(string='Актив', required=True)
    quantity = fields.Float(
        string='Количество', digits=(16, 8), required=True,
        help='Плюс — пришло, минус — ушло. Знак и есть направление.')
    valuation = fields.Monetary(
        string='Оценка', currency_field='currency_id',
        help='Пересчёт на момент операции, справочно.')
    currency_id = fields.Many2one(related='wallet_id.currency_id', store=True)

    # Вторая нога обмена. У обычной операции пуста — это не пропуск, а
    # свойство: обменивают на что-то, а получают просто так.
    swap_symbol = fields.Char(string='Обменяно на')
    swap_quantity = fields.Float(string='Получено', digits=(16, 8))
    swap_network_id = fields.Many2one(
        'coop.wallet.network', string='Сеть получения',
        help='У обмена ноги бывают в разных сетях.')

    peer_address = fields.Char(
        string='Адрес второй стороны',
        help='Внешний адрес. Если вторая сторона — участник платформы, '
             'она указана отдельно.')
    peer_partner_id = fields.Many2one(
        'res.partner', string='Участник', index=True,
        help='Заполняется, когда вторая сторона — участник платформы: по '
             'внешнему адресу человека не узнать.')

    tx_hash = fields.Char(string='Хэш операции', index=True)
    explorer_url = fields.Char(
        string='Проверить в сети', compute='_compute_explorer_url',
        help='Ссылка в обозреватель сети. Без неё хэш — строка, которую '
             'некуда проверить.')

    state = fields.Selection([
        ('pending', 'Ожидает подтверждения сети'),
        ('confirmed', 'Подтверждена'),
        ('failed', 'Отклонена сетью'),
    ], string='Состояние', default='confirmed', required=True, index=True,
        tracking=True,
        help='Перевод в сети подтверждается не мгновенно, а иногда не '
             'проходит вовсе. Показывать только свершившееся значит '
             'оставлять человека в неведении, где его деньги.')

    @api.depends('tx_hash', 'network_id.explorer_url')
    def _compute_explorer_url(self):
        for record in self:
            base = record.network_id.explorer_url
            record.explorer_url = (base + record.tx_hash) if (base and record.tx_hash) else False

    def action_open_explorer(self):
        self.ensure_one()
        if not self.explorer_url:
            raise UserError(_(
                'У этой сети не указан обозреватель, а без него хэш проверить '
                'негде. Обозреватель задаётся в справочнике сетей.'))
        return {'type': 'ir.actions.act_url', 'url': self.explorer_url, 'target': 'new'}
