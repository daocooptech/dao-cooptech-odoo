# -*- coding: utf-8 -*-
from odoo import api, models

# Разделы, которые появляются во включённом режиме. Они не хранятся в
# меню участника: полномочия — состояние, а не подписка, и меню не должно
# помнить их между включениями. Выключил переключатель — пунктов нет.
ADMIN_ITEMS = [
    ('Полномочия', 'fa-shield', 'coop_admin.action_coop_admin_grant'),
    ('Участники узла', 'fa-users', 'base.action_res_users'),
    ('Настройки', 'fa-cog', 'base_setup.action_general_configuration'),
    ('Модели и поля', 'fa-database', 'base.action_model_model'),
    ('Журнал действий', 'fa-history', 'base.action_ir_logging'),
]


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
