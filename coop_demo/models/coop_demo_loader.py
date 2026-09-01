# -*- coding: utf-8 -*-
from odoo import api, models

from ..data import load_people


class CoopDemoLoader(models.AbstractModel):
    """Точка входа для наполнения каталогов из макета.

    Абстрактная модель, а не хук установки: хук выполняется только при
    установке, а данные каталогов нужно перезаливать и при обновлении
    модуля — иначе изменения в макете не доезжают до стенда, пока кто-то
    не пересоберёт базу с нуля.
    """
    _name = 'coop.demo.loader'
    _description = 'Загрузчик данных из макета'

    @api.model
    def load_all(self):
        load_people.load_people(self.env)
        return True
