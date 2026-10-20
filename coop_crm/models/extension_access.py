from odoo import api, models


class CoopExtensionConnection(models.Model):
    """Модуль коробки у организации — руководителю и выбранным (решение 476).

    Руководитель подключает модуль в меню организации и отмечает, кому
    его открыть («Доступ у»). Группы модуля выдаются этим людям при
    компании учёта организации — как приложения организации в
    `org_apps.py`, той же синхронизацией, — и снимаются, когда человека
    убрали из списка или модуль убрали из меню.
    """
    _inherit = 'coop.extension.connection'

    def _coop_org_box(self):
        return self.filtered(
            lambda c: c.partner_id.is_company and c.extension_id.source != 'cooptech')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for conn in records._coop_org_box():
            # Данным модуля нужна компания организации, иначе они лягут в
            # общую компанию платформы; РСБУ-слой — не сейчас (решение 480).
            conn.partner_id.sudo()._coop_ensure_company(rsbu=False)
        records._coop_sync_access(records.access_user_ids)
        return records

    def write(self, vals):
        before = self.access_user_ids
        res = super().write(vals)
        if 'access_user_ids' in vals:
            self._coop_sync_access(before | self.access_user_ids)
        return res

    def unlink(self):
        users = self.access_user_ids
        # Подключения уже не будет — его группы синхронизация должна
        # узнать из контекста, иначе не сочтёт их своими и не снимет.
        groups = self.env['res.groups'].union(
            self.env['res.groups'],
            *[c.extension_id._coop_module_groups() for c in self._coop_org_box()])
        res = super().unlink()
        self.with_context(coop_revoke_group_ids=groups.ids)._coop_sync_access(users)
        return res

    def _coop_sync_access(self, users):
        # Пустой список синхронизация поняла бы как «всех» — не зовём.
        if users:
            self.env['res.users'].sudo()._coop_sync_accounting_access(users=users)


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _coop_company_grants(self, user):
        grants = super()._coop_company_grants(user)
        Groups = self.env['res.groups']
        conns = self.env['coop.extension.connection'].sudo().search(
            [('access_user_ids', 'in', user.id)])
        for conn in conns._coop_org_box():
            company = conn.partner_id.coop_company_id
            # Вышел из организации — доступ уходит, даже если из списка
            # его не убрали.
            if not company or user not in conn.coop_member_user_ids:
                continue
            groups = conn.extension_id._coop_module_groups()
            if groups:
                grants[company] = grants.get(company, Groups) | groups
        return grants

    @api.model
    def _coop_revocable_groups(self):
        """Группы модулей коробки, подключённых организациями.

        Кроме тех, что движок даёт каждому новому пользователю: их
        синхронизация не трогает.
        """
        conns = self.env['coop.extension.connection'].sudo().search(
            [('partner_id.is_company', '=', True)])._coop_org_box()
        groups = self.env['res.groups'].union(
            *[c.extension_id._coop_module_groups() for c in conns]) \
            if conns else self.env['res.groups']
        groups |= self.env['res.groups'].browse(self.env.context.get('coop_revoke_group_ids', []))
        return super()._coop_revocable_groups() | (groups - self._default_groups())
