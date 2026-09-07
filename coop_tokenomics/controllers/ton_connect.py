# -*- coding: utf-8 -*-
"""Манифест TON Connect и приём подключённого кошелька.

Кошелёк не подключается к чему попало: прежде чем показать участнику
запрос, он скачивает манифест приложения и показывает из него название и
адрес — чтобы человек видел, кому именно даёт доступ. Манифест обязан
лежать по публичному HTTPS-адресу того же приложения, поэтому он и
отдаётся здесь, а не лежит файлом в модуле: имя и адрес платформы берутся
из настроек, а не вписываются в код.
"""
import json
import logging

from odoo import _, fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class CoopTonConnect(http.Controller):

    @http.route('/tonconnect-manifest.json', type='http', auth='public',
                methods=['GET'], csrf=False)
    def manifest(self, **kwargs):
        """Манифест приложения для кошельков TON."""
        params = request.env['ir.config_parameter'].sudo()
        base = params.get_param('web.base.url', '')
        # Название берётся отдельным параметром, а не из карточки
        # компании: там стоит юридическое имя со всеми уточнениями
        # («рабочая группа»), а кошелёк показывает эту строку человеку —
        # он должен узнать платформу, а не гадать, кому даёт доступ.
        data = {
            'url': base,
            'name': params.get_param('coop.platform_name', 'ДАО КООПТЕХ'),
            'iconUrl': '%s/coop_website/static/src/img/cooptech-logo.png' % base,
            'termsOfUseUrl': '%s/rules' % base,
            'privacyPolicyUrl': '%s/rules' % base,
        }
        return request.make_response(
            json.dumps(data, ensure_ascii=False),
            headers=[('Content-Type', 'application/json; charset=utf-8'),
                     # Манифест читает кошелёк со своей стороны, поэтому
                     # он должен быть доступен из любого источника.
                     ('Access-Control-Allow-Origin', '*'),
                     ('Cache-Control', 'public, max-age=600')])

    @http.route('/coop/ton/connected', type='json', auth='user',
                methods=['POST'])
    def connected(self, address=None, network=None, **kwargs):
        """Запомнить адрес подключённого кошелька.

        Проверять подпись здесь нечем и незачем: адрес — не секрет и не
        полномочие. Всё, что им можно сделать на платформе, — получить
        токены; распорядиться ими сможет только владелец ключа.

        Сеть приходит от кошелька строкой идентификатора: «-239» —
        основная, «-3» — тестовая.
        """
        if not address:
            return {'ok': False, 'error': _('Кошелёк не прислал адрес.')}
        partner = request.env.user._coop_acting_partner()
        partner.sudo().write({
            'coop_ton_address': address,
            'coop_ton_network': 'mainnet' if str(network) == '-239' else 'testnet',
            'coop_ton_connected_on': fields.Datetime.now(),
        })
        _logger.info('Кошелёк подключён: участник %s', partner.display_name)
        return {'ok': True, 'address': partner.coop_ton_address,
                'network': partner.coop_ton_network}
