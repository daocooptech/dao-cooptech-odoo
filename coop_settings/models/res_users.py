# -*- coding: utf-8 -*-
from odoo import _, api, models


class ResUsers(models.Model):
    """Язык и часовой пояс — настройки учётной записи, а не карточки.

    Держатся у пользователя, а не у контакта: язык интерфейса и пояс —
    это про того, кто вошёл, а не про то, кого показывают. Переключившись
    на организацию, человек не меняет ни язык, ни часы.
    """

    _inherit = 'res.users'

    @api.model
    def action_coop_open_region_settings(self):
        view = self.env.ref('coop_settings.view_coop_settings_region_form',
                            raise_if_not_found=False)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Язык и регион'),
            'res_model': 'res.users',
            'res_id': self.env.user.id,
            'view_mode': 'form',
            'views': [(view.id if view else False, 'form')],
            'target': 'current',
            'context': {'coop_settings': True},
        }
