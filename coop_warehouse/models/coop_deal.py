# -*- coding: utf-8 -*-
"""Сделка по складскому месту — обычная сделка платформы, с поправкой.

Отдельной «складской сделки» на платформе нет и не должно быть: у места
те же стороны, тот же акт приёмки, тот же спор и те же отзывы, что у
техники или работы. Не хватает ровно двух вещей — какого склада это
касается и сколько места занято: без объёма склад не сможет посчитать,
что у него осталось свободного, и на бирже повиснет место, которого нет.
"""
from odoo import api, fields, models

from .coop_warehouse import TERM_KINDS


class CoopDeal(models.Model):
    _inherit = 'coop.deal'

    warehouse_id = fields.Many2one(
        'coop.warehouse', string='Склад', index=True,
        help='Заполнено у сделок о складском месте. Склад считает по ним '
             'сданный другим объём.')
    warehouse_offer_id = fields.Many2one(
        'coop.warehouse.offer', string='Объявление на бирже', index=True)
    warehouse_volume = fields.Float(
        string='Объём места', digits=(12, 1),
        help='Сколько места занято по этой сделке, в единице учёта склада.')
    warehouse_terms = fields.Selection(
        TERM_KINDS, string='Условие по складу')
    warehouse_unit = fields.Selection(
        related='warehouse_id.capacity_unit', string='Единица склада')

    @api.onchange('warehouse_offer_id')
    def _onchange_warehouse_offer(self):
        """Из объявления подставляем склад, объём и город.

        Переписывать это руками — способ получить сделку на сорок
        паллетомест по объявлению, где их было двадцать.
        """
        for record in self:
            offer = record.warehouse_offer_id
            if not offer:
                continue
            record.warehouse_id = offer.warehouse_id
            record.warehouse_volume = offer.volume
            record.city = offer.city or record.city
            if offer.term_ids and not record.warehouse_terms:
                record.warehouse_terms = offer.term_ids[0].kind
