# -*- coding: utf-8 -*-
import re

from odoo import api, models

from ..node_path import NODE_PATH


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Имя узла для браузера: роутер строит по нему адреса /nn1/…"""
        info = super().session_info()
        info['coop_node_path'] = NODE_PATH
        return info

    # «Odoo» в переводах веб-клиента — «Ошибка сервера Odoo», «Сессия Odoo
    # истекла» — меняется на название платформы (решение 442). Rudoo-модуль
    # web_debranding (OPL-1) пытался делать то же, но переопределял метод на
    # чужой модели и под старым именем, и в Odoo 19 не действовал.
    # «Odoo S.A.» и «Odoo.com» не трогаем: это авторство и адрес, а не бренд
    # платформы.
    _ODOO_WORD = re.compile(r'\bOdoo\b(?!\s*S\.A\.)(?!\.com)')
    _PLATFORM_NAME = 'ДАО КООПТЕХ'

    @api.model
    def _get_translations_for_webclient(self, modules, lang):
        per_module, lang_params = super()._get_translations_for_webclient(modules, lang)
        result = {}
        for module, values in per_module.items():
            messages = values.get('messages', ())
            if any(self._ODOO_WORD.search(m.get('string') or '') for m in messages):
                values = dict(values, messages=tuple(
                    dict(m, string=self._ODOO_WORD.sub(self._PLATFORM_NAME, m.get('string') or ''))
                    for m in messages))
            result[module] = values
        return result, lang_params
