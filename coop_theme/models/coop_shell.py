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

    # ── Переключатель «действую от имени…» ───────────────────────────────
    #
    # Организация — сторона обязательства, но кнопку всегда нажимает
    # человек. Переключатель хранится на сервере: при разборе спора надо
    # восстановить, от чьего имени была нажата кнопка, а не поверить тому,
    # что осталось в чужом браузере.

    @api.model
    def acting_options(self):
        user = self.env.user
        return {
            'current': user.coop_acting_as_id.id or user.partner_id.id,
            'self': user.partner_id.id,
            'options': [
                {'id': partner.id,
                 'name': partner.display_name,
                 'isCompany': partner.is_company}
                for partner in user.coop_actor_partner_ids
            ],
        }

    @api.model
    def set_acting(self, partner_id):
        """Переключиться на организацию или обратно на себя.

        Свой партнёр в списке есть наравне с организациями — это и есть
        «действую от себя», и отдельного пункта «выключить» не нужно.
        """
        user = self.env.user
        partner_id = int(partner_id or 0)
        if partner_id == user.partner_id.id:
            partner_id = False
        user.action_coop_act_as(partner_id)
        return True
