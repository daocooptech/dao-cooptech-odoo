# -*- coding: utf-8 -*-
from odoo import api, models


class CoopShell(models.AbstractModel):
    """Разрешение внешних идентификаторов действий для бокового меню.

    Меню собирается на клиенте по списку разделов, а ссылаться на действия
    приходится по внешним идентификаторам: числовые в разных базах разные.
    Разрешать их из браузера напрямую нельзя — на `ir.model.data` у
    участника нет прав, и не должно быть.

    Отсутствующий идентификатор не ошибка: узел может стоять без части
    модулей, и пункт меню тогда просто не откроется, а не уронит оболочку.
    """
    _name = 'coop.shell'
    _description = 'Оболочка платформы'

    @api.model
    def resolve_actions(self, xmlids):
        resolved = {}
        for xmlid in xmlids or []:
            record = self.env.ref(xmlid, raise_if_not_found=False)
            # Только действия. Внешний идентификатор может указывать на что
            # угодно — на пункт меню, на представление, на запись справочника,
            # — и число оттуда откроет не тот экран или не откроет никакой.
            if record and record._name.startswith('ir.actions.'):
                resolved[xmlid] = record.id
        return resolved
