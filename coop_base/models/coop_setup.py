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
        self._setup_home()
        return True

    def _setup_home(self):
        """Один адрес, который всегда открывает платформу.

        Без этого `/odoo` показывает то последнее, где человек был, а
        первый вход — список приложений Odoo. Оба варианта заставляют
        каждый раз искать, куда идти, и просить ссылку на нужный экран.

        Домашним ставится каталог людей: это первый перенесённый раздел
        платформы, и он есть у всех. Когда появится «Моя страница»,
        домашним станет она — там и место первому экрану.

        Тем, кто уже выбрал себе домашний экран, не мешаем: своё
        решение человека важнее нашего умолчания.
        """
        home = self.env.ref(
            'coop_people.action_coop_people', raise_if_not_found=False)
        if not home:
            return
        users = self.env['res.users'].sudo().search([
            ('share', '=', False), ('action_id', '=', False)])
        if users:
            users.write({'action_id': home.id})
            _logger.info('Домашний экран задан для %s учётных записей', len(users))

        # Ссылки, которые Odoo рассылает в письмах и уведомлениях, строятся
        # от этого параметра. Незакреплённый, он переписывается адресом
        # последнего входа — и в письме оказывается адрес, по которому
        # никто больше не зайдёт.
        params = self.env['ir.config_parameter'].sudo()
        if not params.get_param('web.base.url.freeze'):
            params.set_param('web.base.url.freeze', 'True')

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
