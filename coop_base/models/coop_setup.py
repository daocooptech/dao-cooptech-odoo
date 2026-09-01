# -*- coding: utf-8 -*-
"""Разовые настройки платформы, которые нельзя сделать данными.

Часть записей Odoo объявлена в базовом модуле с защитой от обновления
(noupdate). Переопределить их из своего модуля нельзя: загрузчик видит
защиту и молча пропускает правку, а на экране остаётся старое значение —
и понять по коду, почему, невозможно. Такие вещи делаются кодом.
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class CoopSetup(models.AbstractModel):
    _name = 'coop.setup'
    _description = 'Настройки платформы'

    @api.model
    def apply(self):
        self._setup_currency()
        return True

    def _setup_currency(self):
        """Знак рубля вместо «руб».

        В макете цены написаны через ₽, и разнобой между макетом и
        движком читается как небрежность. Правится сама валюта, а не
        каждое место показа: иначе знак пришлось бы дублировать во всех
        карточках, списках и отчётах.
        """
        rub = self.env['res.currency'].sudo().with_context(
            active_test=False).search([('name', '=', 'RUB')], limit=1)
        if rub and rub.symbol != '₽':
            rub.write({'symbol': '₽', 'position': 'after'})
            _logger.info('Знак рубля установлен: ₽')
