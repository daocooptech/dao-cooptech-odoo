# -*- coding: utf-8 -*-
from odoo import api, models

# Раздел «Аналитики» — у того, у кого подключён его модуль (решение 708,
# кусок 3 задачи 494). Деньги, Сделки, Доверие, Проекты стоят на разделах
# платформы (`MAIN_ITEMS` — кошелёк, сделки, проекты): они у всех, им
# записи здесь не нужно. Разделы организаций (Продажи … Мероприятия)
# закрыты группами — группы выдаёт подключение модуля организацией
# (`coop_crm/models/extension_access.py`), отдельной проверки не нужно.
SECTION_MODULES = {
    'coop_analytics.menu_coop_an_sec_dex': 'coop_crypto_exchange',
    'coop_analytics.menu_coop_an_sec_courses': 'coop_education',
}


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _load_menus_blacklist(self):
        """Пункт раздела без подключённого модуля в меню не грузится.

        Лицо — то, от имени которого человек действует сейчас: у
        организации свой набор модулей. Вкладки раздела уходят вместе с
        ним — движок отбрасывает детей скрытого пункта.
        """
        hidden = list(super()._load_menus_blacklist())
        Ext = self.env['coop.extension'].sudo()
        connected = set(Ext.browse(list(Ext._coop_connected_ids())).exists().mapped('module_name'))
        for xmlid, module in SECTION_MODULES.items():
            if module in connected:
                continue
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                hidden.append(menu.id)
        return hidden


class CoopExtensionConnection(models.Model):
    """Меню грузится один раз на участника и кэшируется (`load_menus`):
    подключили или убрали модуль — кэш сбрасывается, иначе раздел
    «Аналитики» появился бы только после перезапуска сервера."""
    _inherit = 'coop.extension.connection'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env.transaction.invalidate_ormcache('default')
        return records

    def unlink(self):
        res = super().unlink()
        self.env.transaction.invalidate_ormcache('default')
        return res


class ResUsers(models.Model):
    _inherit = 'res.users'

    def action_coop_act_as(self, partner_id=False):
        # Сменилось лицо — сменился и набор подключённых модулей.
        res = super().action_coop_act_as(partner_id)
        self.env.transaction.invalidate_ormcache('default')
        return res
