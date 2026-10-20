# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

# Что включённый режим даёт всегда. Одной группы системного
# администратора мало: права разделов (бухгалтерия, склад, продажи…) у
# движка — отдельные группы, и «Выставление счетов» у `dashkevich` с
# включённым режимом отвечало «нет доступа к панели бухгалтерии». Поэтому
# сверх этих двух — все группы владельца площадки (`base.user_admin`),
# владелец 20.10.2026: «у dashkevich должен быть полный доступ ко всему как
# у владельца площадки».
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
    coop_admin_added_group_ids = fields.Many2many(
        'res.groups', 'coop_admin_added_group_rel', 'user_id', 'group_id',
        string='Группы, добавленные режимом', copy=False,
        help='Снимаются при выключении режима. Группы, которые были у '
             'человека до включения, сюда не попадают и остаются.')
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

    def _coop_admin_wanted_groups(self):
        """Набор режима: обе группы режима и всё, что есть у владельца."""
        groups = self.env['res.groups']
        for xml_id in ADMIN_GROUPS:
            groups |= self.env.ref(xml_id, raise_if_not_found=False) or groups
        owner = self.env.ref('base.user_admin', raise_if_not_found=False)
        if owner:
            groups |= owner.group_ids.filtered(lambda g: not g.share)
        return groups

    def _coop_sync_admin_groups(self):
        """Привести состав групп к состоянию переключателя.

        Включён — недостающие группы владельца дописываются и запоминаются;
        выключен — снимаются только запомненные (и две группы режима), свои
        группы человека остаются.
        """
        for user in self:
            if user.coop_admin_active and user.coop_admin_granted:
                missing = user._coop_admin_wanted_groups() - user.group_ids
                if missing:
                    user.write({
                        'group_ids': [(4, g.id) for g in missing],
                        'coop_admin_added_group_ids': [(4, g.id) for g in missing],
                    })
                continue
            drop = user.coop_admin_added_group_ids
            for xml_id in ADMIN_GROUPS:
                drop |= self.env.ref(xml_id, raise_if_not_found=False) or drop
            drop &= user.group_ids
            vals = {}
            if user.coop_admin_added_group_ids:
                vals['coop_admin_added_group_ids'] = [(5, 0, 0)]
            if drop:
                vals['group_ids'] = [(3, g.id) for g in drop]
            if vals:
                user.write(vals)
