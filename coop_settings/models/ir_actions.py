# -*- coding: utf-8 -*-
from odoo import models


class IrActionsActWindow(models.Model):
    """Окно движка «Изменить мои настройки» — на «Настройки → Аккаунт».

    Прямая ссылка `/odoo/action-base.action_res_users_my` загружает
    действие по внешнему имени, мимо `res.users.action_get`. Подменяется
    словарь действия, а не сама запись: она нужна движку как есть.
    """

    _inherit = 'ir.actions.act_window'

    def _get_action_dict(self):
        if len(self) == 1 and self == self.env.ref(
                'base.action_res_users_my', raise_if_not_found=False):
            return self.env['res.partner'].with_env(
                self.env(su=False)).action_coop_open_settings()
        return super()._get_action_dict()
