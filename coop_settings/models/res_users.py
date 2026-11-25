# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.addons.base.models.res_users import check_identity


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
    # Страна сводки кошелька и гражданства — в «Язык и регион» (задача 400,
    # решение 640); хранятся на карточке участника.
    coop_summary_country_id = fields.Many2one(
        related='partner_id.coop_summary_country_id', readonly=False,
        user_writeable=True)
    coop_citizenship_ids = fields.Many2many(
        related='partner_id.coop_citizenship_ids', readonly=False,
        user_writeable=True)
    coop_ru_residence_permit = fields.Boolean(
        related='partner_id.coop_ru_residence_permit', readonly=False,
        user_writeable=True)
    coop_currency_rub_only = fields.Boolean(
        compute='_compute_coop_currency_rub_only')

    @api.depends('partner_id.country_id', 'partner_id.coop_fx_resident')
    def _compute_coop_currency_rub_only(self):
        for user in self:
            user.coop_currency_rub_only = user.partner_id._coop_rub_only()

    # Окно движка «Изменить мои настройки» закрыто (№ 302): всё, что в нём
    # было, — во вкладках «Настроек». Его просит меню движка и прямая
    # ссылка; обе ведут в «Настройки → Аккаунт».
    def action_get(self):
        return self.env['res.partner'].action_coop_open_settings()

    # Мастера ключей — с русским заголовком: у движка он строкой в коде,
    # мимо перевода. Сперва движок может вернуть проверку пароля
    # (`check_identity`) — её заголовок не трогаем. Пометка `check_identity`
    # и у переопределения: без неё движок после ввода пароля отказывается
    # вызывать метод (`run_check` проверяет её у вызываемого).
    @check_identity
    def api_key_wizard(self):
        action = super().api_key_wizard()
        if action.get('res_model') == 'res.users.apikeys.description':
            action['name'] = _('Новый ключ API')
        return action

    @check_identity
    def action_create_passkey(self):
        action = super().action_create_passkey()
        if action.get('res_model') == 'auth.passkey.key.create':
            action['name'] = _('Новый ключ доступа')
        return action

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


class ResUsersApikeysDescription(models.TransientModel):
    """Сроки ключа API — по-русски: у движка подписи строками в коде."""

    _inherit = 'res.users.apikeys.description'

    _COOP_DURATION_LABELS = {
        '1': 'Сутки', '30': 'Месяц', '365': 'Год', '0': 'Бессрочно'}

    def _selection_duration(self):
        return [(value, _(self._COOP_DURATION_LABELS.get(value, label)))
                for value, label in super()._selection_duration()]

    @check_identity
    def make_key(self):
        action = super().make_key()
        if action.get('res_model') == 'res.users.apikeys.show':
            action['name'] = _('Ключ API создан')
        return action
