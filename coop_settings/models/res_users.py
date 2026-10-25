# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ResUsers(models.Model):
    """Настройки учётной записи, а не карточки.

    Язык, часовой пояс, пароль, двухфакторная проверка, сеансы — всё это
    про того, кто вошёл, а не про того, кого показывают. Переключившись
    на организацию, человек не меняет ни язык, ни часы, ни свой пароль.
    """

    _inherit = 'res.users'

    # Валюта — участника, а не учётной записи: переключившись на
    # организацию, человек ставит цены в её валюте (решение 482). Здесь —
    # только его собственная, для вкладки «Язык и регион».
    coop_currency_id = fields.Many2one(
        related='partner_id.coop_currency_id', readonly=False)
    coop_currency_rub_only = fields.Boolean(
        compute='_compute_coop_currency_rub_only')

    @api.depends('partner_id.country_id', 'partner_id.coop_fx_resident')
    def _compute_coop_currency_rub_only(self):
        for user in self:
            user.coop_currency_rub_only = user.partner_id._coop_rub_only()

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
