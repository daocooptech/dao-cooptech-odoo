# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoopDeal(models.Model):
    """Сделка глазами уступки: годится ли требование по ней к размещению.

    Денежное требование возникает не из записи на витрине, а из сделки:
    работа принята — акт подтверждён обеими сторонами, — а деньги ещё не
    уплачены. Оба условия уже хранятся в `coop_deals`, здесь они только
    собраны в один признак, чтобы витрина не повторяла эту проверку в
    трёх местах и не разошлась с ней при первой же правке.

    Запрет уступки — не усмотрение платформы: требования, неразрывно
    связанные с личностью кредитора, не уступаются по прямому запрету
    ст. 383 ГК, остальные — когда уступку запретил договор сторон
    (п. 2 ст. 382 ГК). Признак полем, а не строчкой мелким шрифтом:
    текст проверяет человек, поле проверяет форма.
    """
    _inherit = 'coop.deal'

    cession_forbidden = fields.Boolean(
        string='Уступка требования запрещена',
        help='Требование связано с личностью кредитора либо его уступку '
             'запретил договор. К размещению не принимается.')
    cession_forbidden_reason = fields.Char(
        string='Основание запрета',
        help='«Пункт 8.4 договора» — видно и вам, и проверяющему, а не '
             'только тому, кто ставил галочку.')

    cession_ids = fields.One2many(
        'coop.cession', 'deal_id', string='Предложения об уступке')

    can_be_ceded = fields.Boolean(
        string='Требование можно уступить', compute='_compute_can_be_ceded',
        store=True,
        help='Акт подтверждён обеими сторонами, остаток не уплачен, '
             'запрета нет.')

    @api.depends('act_confirmed_a', 'act_confirmed_b', 'amount_due',
                 'cession_forbidden', 'state')
    def _compute_can_be_ceded(self):
        for record in self:
            record.can_be_ceded = bool(
                record.act_confirmed_a
                and record.act_confirmed_b
                and record.amount_due > 0
                and not record.cession_forbidden
                and record.state not in ('cancelled', 'disputed')
            )
