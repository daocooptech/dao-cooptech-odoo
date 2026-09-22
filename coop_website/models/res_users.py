# -*- coding: utf-8 -*-
from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _signup_create_user(self, values):
        """Зарегистрировавшийся становится участником платформы.

        Штатная регистрация Odoo копирует шаблон портального
        пользователя: человек заводит учётную запись, входит — и
        попадает на `/my`, портальную оболочку, где платформы нет вовсе.
        Для кооператива это бессмысленно: участник и есть тот, кто
        пользуется разделами, а не смотрит на свои заказы со стороны.

        Поэтому после создания учётная запись переводится во внутреннюю,
        а его карточка помечается участником платформы — тем же
        признаком, по которому человек попадает в каталог людей.

        Решение владельца от 15 сентября 2026: на время испытаний
        человек заводит учётную запись и сразу входит по логину и
        паролю.

        **Это открывает вход в платформу всякому, кто зарегистрируется.**
        Пока регистрация свободная (`auth_signup.invitation_scope` =
        `b2c`), иначе и быть не может. Когда испытания кончатся,
        закрывать надо именно свободную регистрацию, а не этот метод:
        приглашённый участник должен попадать внутрь так же.

        Выключается параметром `coop.signup_creates_participant` в
        значении `False` — тогда регистрация работает по-штатному и
        заводит портального.
        """
        user = super()._signup_create_user(values)
        if not self._coop_signup_makes_participant():
            return user
        internal = self.env.ref('base.group_user', raise_if_not_found=False)
        portal_one = self.env.ref('base.group_portal', raise_if_not_found=False)
        if internal:
            commands = [(4, internal.id)]
            if portal_one:
                commands.append((3, portal_one.id))
            user.sudo().write({'group_ids': commands})
        if user.partner_id:
            user.partner_id.sudo().write({'coop_is_participant': True})
        # Домашний экран ставится в `create`, но там учётная запись была
        # ещё портальной и его пропустили. Ставим теперь.
        home = self._coop_home_action()
        if home and not user.action_id:
            user.sudo().action_id = home.id
        return user

    @api.model
    def _coop_signup_makes_participant(self):
        value = self.env['ir.config_parameter'].sudo().get_param(
            'coop.signup_creates_participant', 'True')
        return str(value).strip().lower() not in ('0', 'false', 'нет')
