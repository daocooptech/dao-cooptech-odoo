# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.tools.binary import BinaryBytes
from odoo.tools.misc import file_open


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def coop_city_suggestions(self, limit=300):
        """Города для подсказки в поле «Город» (виджет `coop_city`).

        Те, что уже встречаются у людей и организаций платформы, частые —
        первыми: так же подсказывает фильтр «Город» в каталогах. Владелец
        18.11.2026 про подписку на задачи: «город не находится когда я
        начинаю вводить» — поле было голым текстом без подсказки.
        """
        groups = self.sudo()._read_group([('city', '!=', False)], ['city'], ['__count'],
                                         order='__count desc', limit=limit)
        seen, cities = set(), []
        for city, _count in groups:
            name = (city or '').strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                cities.append(name)
        return cities

    @api.model
    def _coop_team_logo(self):
        """Знак у «Рабочей группы платформы» (владелец 12.10.2026): лого coop,
        как в шапке, и «team» под ним — вместо серой заглушки.

        Рабочая группа — партнёр служебной учётной записи движка
        (`base.partner_admin`, решение 126). Картинку ставим, только пока
        своей нет: заменённую руками обновление не перетирает.
        """
        partner = self.env.ref('base.partner_admin', raise_if_not_found=False)
        if not partner or partner.sudo().image_1920:
            return False
        with file_open('coop_theme/static/src/img/team-logo.png', 'rb') as handle:
            # Движок 20 пишет двоичные поля сырыми байтами в BinaryBytes,
            # а не base64: строка base64 падает TypeError при обновлении.
            partner.sudo().image_1920 = BinaryBytes(handle.read())
        return True
