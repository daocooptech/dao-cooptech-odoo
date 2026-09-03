# -*- coding: utf-8 -*-
import json

from odoo import fields, models


class ResUsers(models.Model):
    """Память о том, какие расширения участнику уже предлагали.

    Без неё «нет пункта в меню» и «пункт ещё не предлагали» — одно и то
    же, и убранное участником расширение возвращалось при следующем же
    открытии страницы. Убрать его было нельзя вовсе, хотя расширения для
    того и отделены от разделов, что они личное дело каждого.

    Хранится списком названий, а не ссылками на пункты: пункт участник
    удаляет, а память о предложении должна пережить удаление — в том и
    смысл. Поле служебное и правится только самой оболочкой, под sudo:
    участнику незачем ни читать его, ни менять.
    """

    _inherit = 'res.users'

    coop_sidebar_defaults = fields.Char(
        string='Предложенные расширения', copy=False,
        help='Служебное: какие расширения из списка по умолчанию участнику '
             'уже показывали. Убранное им расширение не возвращается.')

    def _coop_sidebar_defaults(self):
        self.ensure_one()
        try:
            names = json.loads(self.sudo().coop_sidebar_defaults or '[]')
        except ValueError:
            names = []
        if not isinstance(names, list):
            names = []
        return set(names)

    def _coop_remember_sidebar_defaults(self, names):
        self.ensure_one()
        value = json.dumps(sorted(set(names)), ensure_ascii=False)
        if self.sudo().coop_sidebar_defaults != value:
            self.sudo().coop_sidebar_defaults = value
        return True
