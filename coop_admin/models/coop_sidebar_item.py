# -*- coding: utf-8 -*-
from odoo import api, models

# Разделы, которые появляются во включённом режиме. Они не хранятся в
# меню участника: полномочия — состояние, а не подписка, и меню не должно
# помнить их между включениями. Выключил переключатель — пунктов нет.
# Значки — контуры Tabler из `coop_theme/static/src/js/icons.js`, каждый не
# занят другим пунктом меню (владелец 15.11.2026, № 456: в режиме
# администратора вместо значков стоял текст — имена Material движок 20
# шрифтом больше не рисует).
# С 28.11.2026 пунктов режима в левой планке нет — они в «Настройках»
# (`views/coop_admin_settings_menus.xml`; владелец: «пункты меню которые
# появляются при переключении на режим админа тоже перенести в
# настройки»). «Настройки узла» — тот же экран, что «Общие настройки».
# Список оставлен пустым: дописывание ниже — на случай пункта, которому
# в «Настройках» не место.
ADMIN_ITEMS = []


class CoopSidebarItem(models.Model):
    _inherit = 'coop.sidebar.item'

    @api.model
    def items_for_current_user(self):
        """Дописать административные разделы, если режим включён.

        Дописываются на лету, а не создаются записями: иначе выключенный
        переключатель оставлял бы пункты в меню, и «выключено» перестало
        бы что-либо значить.
        """
        items = super().items_for_current_user()
        user = self.env.user
        if not (user.coop_admin_granted and user.coop_admin_active):
            return items
        for index, (name, icon, xmlid) in enumerate(ADMIN_ITEMS):
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if not action:
                continue
            items.append({
                'id': 'admin-%s' % index,
                'label': name,
                'icon': icon,
                'actionId': action.id,
                'section': 'admin',
            })
        return items
