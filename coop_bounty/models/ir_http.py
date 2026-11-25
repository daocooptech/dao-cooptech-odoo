# -*- coding: utf-8 -*-
"""Вошедший — внутри платформы (№ 471, владелец 17.11 и 25.11.2026).

Публичная «Помощь проекту» нужна гостю. Участник с того же адреса
попадает на карточку нашего проекта внутри платформы — иначе он видит
сайт со своим меню и не понимает, куда делась платформа.
"""
from odoo import models
from odoo.http import request

HELP_PAGE = '/help-project'


def coop_inside(url):
    """Переход внутрь платформы для участника, иначе None.

    В рамке открыт редактор сайта — там страница нужна сама.
    """
    if not request.env.user._is_internal():
        return None
    if request.httprequest.headers.get('Sec-Fetch-Dest') == 'iframe':
        return None
    return request.redirect(url, 303)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _serve_page(cls):
        if request.httprequest.path.rstrip('/') == HELP_PAGE:
            inside = coop_inside('/odoo/help-project')
            if inside:
                return inside
        return super()._serve_page()
