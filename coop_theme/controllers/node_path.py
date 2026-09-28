# -*- coding: utf-8 -*-
"""Веб-клиент по адресу узла: /nn1/…; старый /odoo/… переадресует туда.

Маршрут расширяется, а не подменяется: список путей наследника сливается с
родительским, тип, доступ и признак «только чтение» остаются от движка.
"""
from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.home import Home

from ..node_path import NODE_PATH

PREFIX = '/' + NODE_PATH


class CoopNodeHome(Home):

    @http.route(['/web', '/odoo', '/odoo/<path:subpath>', '/scoped_app/<path:subpath>',
                 PREFIX, PREFIX + '/<path:subpath>'])
    def web_client(self, s_action=None, **kw):
        path = request.httprequest.path
        if path == '/odoo' or path.startswith('/odoo/'):
            # Ссылки из писем, переадресации движка после входа, закладки —
            # всё, что ещё смотрит на /odoo, попадает на адрес узла.
            target = PREFIX + path[len('/odoo'):]
            query = request.httprequest.query_string.decode()
            return request.redirect(target + ('?' + query if query else ''), code=302)
        return super().web_client(s_action=s_action, **kw)
