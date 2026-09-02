# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

# Что именно даёт включённый режим. Группа системного администратора
# Odoo — это и есть «полный доступ на чтение и запись всего»: она снимает
# правила уровня записи и открывает служебные разделы.
ADMIN_GROUPS = ('base.group_system', 'coop_base.group_coop_platform')


class ResUsers(models.Model):
    _inherit = 'res.users'

    coop_admin_grant_ids = fields.One2many(
        'coop.admin.grant', 'user_id', string='Решения о полномочиях')
    coop_admin_granted = fields.Boolean(
        string='Полномочия выданы', compute='_compute_coop_admin_granted',
        store=True,
        help='Есть действующее решение команды. Само по себе полномочий '
             'не включает — их включает переключатель.')
    coop_admin_active = fields.Boolean(
        string='Режим администратора включён', default=False, copy=False,
        help='Пока выключен, человек ходит по платформе как обычный '
             'участник и видит ровно то же, что все.')

    @api.depends('coop_admin_grant_ids.state')
    def _compute_coop_admin_granted(self):
        for user in self:
            user.coop_admin_granted = bool(user.coop_admin_grant_ids.filtered(
                lambda g: g.state == 'granted'))

    # ── Переключатель ───────────────────────────────────────────────────

    @api.model
    def coop_admin_state(self):
        """Что показать в переключателе. Читается оболочкой при загрузке."""
        user = self.env.user
        return {
            'granted': user.coop_admin_granted,
            'active': user.coop_admin_active,
        }

    @api.model
    def coop_admin_toggle(self):
        """Включить или выключить режим администратора.

        Через sudo, потому что рядовой участник не вправе править состав
        своих групп — и не должен: включение разрешено ровно тем, кому
        полномочия выданы решением.
        """
        user = self.env.user
        if not user.coop_admin_granted:
            raise UserError(_(
                'Административные полномочия вам не выдавались. Их '
                'выдаёт команда голосованием.'))
        user.sudo().coop_admin_active = not user.coop_admin_active
        user.sudo()._coop_sync_admin_groups()
        # Пункты меню дописываются при следующей загрузке оболочки —
        # переключение перезагружает страницу, потому что меняется состав
        # групп, а он читается один раз при входе.
        return {'granted': True, 'active': user.coop_admin_active}

    def _coop_sync_admin_grant(self):
        """Пересчитать признак и, если полномочия сняты, погасить режим."""
        for user in self:
            user._compute_coop_admin_granted()
            if not user.coop_admin_granted:
                user.coop_admin_active = False
            user._coop_sync_admin_groups()

    def _coop_sync_admin_groups(self):
        """Привести состав групп к состоянию переключателя."""
        for user in self:
            for xml_id in ADMIN_GROUPS:
                group = self.env.ref(xml_id, raise_if_not_found=False)
                if not group:
                    continue
                wanted = user.coop_admin_active and user.coop_admin_granted
                inside = group in user.all_group_ids
                if wanted and not inside:
                    user.write({'group_ids': [(4, group.id)]})
                elif not wanted and inside:
                    user.write({'group_ids': [(3, group.id)]})
