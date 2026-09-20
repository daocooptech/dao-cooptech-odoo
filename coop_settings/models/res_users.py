# -*- coding: utf-8 -*-
from odoo import _, api, models


class ResUsers(models.Model):
    """Настройки учётной записи, а не карточки.

    Язык, часовой пояс, пароль, двухфакторная проверка, сеансы — всё это
    про того, кто вошёл, а не про того, кого показывают. Переключившись
    на организацию, человек не меняет ни язык, ни часы, ни свой пароль.
    """

    _inherit = 'res.users'

    @api.model
    def action_coop_open_user_settings(self, view_xmlid, name):
        """Открыть вкладку настроек учётной записи.

        Один метод на все вкладки: каждая — та же запись пользователя в
        своём представлении, и отдельное действие под каждую значило бы
        копировать один и тот же десяток строк.
        """
        view = self.env.ref(view_xmlid, raise_if_not_found=False)
        return {
            'type': 'ir.actions.act_window',
            'name': _(name),
            'res_model': 'res.users',
            'res_id': self.env.user.id,
            'view_mode': 'form',
            'views': [(view.id if view else False, 'form')],
            'target': 'current',
            'context': {'coop_settings': True},
        }

    @api.model
    def action_coop_open_region_settings(self):
        return self.action_coop_open_user_settings(
            'coop_settings.view_coop_settings_region_form',
            'Язык и регион')
