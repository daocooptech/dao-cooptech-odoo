# -*- coding: utf-8 -*-
"""Приложения организации (решение 450, ответ владельца 08.10.2026).

«По форме + руководитель», «С доступом»: набор по умолчанию задаёт
группа правовых форм, руководитель (полномочие «Подпись») включает и
выключает. Включённое приложение даёт людям организации с подходящим
полномочием её компанию учёта и группу приложения; выключенное — снимает.
Бухгалтерия в набор не входит: учёт обязаны вести все организации, и
доступ к ней по-прежнему даёт «Бухгалтерия и счета».
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Приложение -> (полномочия, которым оно открывается, группа движка).
# Публикациям и странице учёт организации не открывается ни в каком
# приложении (решение 449: компания учёта — у тех, кто ведёт её дела).
APPS = {
    'crm': (('deal',), 'sales_team.group_sale_salesman_all_leads'),
    'stock': (('deal', 'treasury'), 'stock.group_stock_user'),
    'project': (('sign', 'deal'), 'project.group_project_user'),
    'hr': (('roster', 'powers'), 'hr.group_hr_user'),
}
# «Проекты» по умолчанию выключены у всех (решение 452): организация не
# ведёт своих проектов, пока руководитель не включит, но участвует в
# чужих — команда проекта открывает их её людям и без переключателя.
DEFAULTS = {
    'commercial': ('crm', 'stock', 'hr'),
    'cooperative': ('crm', 'stock'),
    'nonprofit': ('hr',),
    'decentralized': (),
}
FIELDS = ['coop_app_%s' % code for code in APPS]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_app_crm = fields.Boolean(string='CRM')
    coop_app_stock = fields.Boolean(string='Склад')
    coop_app_project = fields.Boolean(string='Проекты')
    coop_app_hr = fields.Boolean(string='Сотрудники')
    coop_can_manage_apps = fields.Boolean(compute='_compute_coop_can_manage_apps')

    @api.depends_context('uid')
    def _compute_coop_can_manage_apps(self):
        user = self.env.user
        for org in self:
            org.coop_can_manage_apps = bool(
                org.is_company and org.id and user.coop_has_power('sign', org))

    def _coop_default_apps(self):
        """Набор по группе правовых форм; без формы — ничего."""
        for org in self:
            code = org.coop_legal_form_group_id.code
            wanted = DEFAULTS.get(code, ())
            super(ResPartner, org).write(
                {'coop_app_%s' % app: app in wanted for app in APPS})
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        fresh = records.filtered(lambda p: p.is_company and not any(p[f] for f in FIELDS))
        fresh.sudo()._coop_default_apps()
        return records

    def write(self, vals):
        changed = set(FIELDS) & set(vals)
        if changed and not self.env.su and not self.env.user.has_group('base.group_system'):
            for org in self:
                if not self.env.user.coop_has_power('sign', org):
                    raise UserError(_(
                        'Приложения организации «%s» включает и выключает '
                        'руководитель.') % org.display_name)
            # Права на запись карточки у руководителя может не быть (её
            # правит держатель «Страницы»): после проверки «Подписи»
            # переключатели пишутся от имени системы.
            app_vals = {k: vals[k] for k in changed}
            vals = {k: v for k, v in vals.items() if k not in changed}
            super(ResPartner, self.sudo()).write(app_vals)
        result = super().write(vals) if vals else True
        if changed:
            orgs = self.filtered('coop_company_id')
            if orgs:
                self.env['res.users'].sudo()._coop_sync_accounting_access(orgs)
        return result

    def _coop_sync_sales_team(self):
        # Выключен CRM — отдел продаж пустеет: лидов организации никто не ведёт.
        result = super()._coop_sync_sales_team()
        Team = self.env['crm.team'].sudo().with_context(active_test=False)
        for org in self.sudo().filtered(lambda o: o.coop_company_id and not o.coop_app_crm):
            Team.search([('company_id', '=', org.coop_company_id.id)]).member_ids = False
        return result

    # ── Переходы в приложения ────────────────────────────────────────

    def _coop_app_action(self, xml_id, name):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(xml_id)
        action['name'] = '%s — %s' % (name, self.name)
        action['domain'] = [('company_id', '=', self.coop_company_id.id)]
        action['context'] = {'default_company_id': self.coop_company_id.id,
                             'coop_catalog': False, 'coop_section': False}
        return action

    def action_coop_app_stock(self):
        return self._coop_app_action('stock.action_picking_tree_all', _('Склад'))

    def action_coop_app_project(self):
        """Проекты, которые организация ведёт или где она вкладчик.

        Не по компании учёта, как остальные приложения: проект сбора
        общий для вкладчиков из разных организаций, и привязка к одной
        компании выкинула бы остальных из команды. Организация-инициатор
        и принятые вкладчики — подписчики проекта (`_project_followers`).
        """
        action = self._coop_app_action('project.open_view_project_all', _('Проекты'))
        action['domain'] = ['|', ('partner_id', '=', self.id),
                            ('message_partner_ids', 'in', [self.id])]
        action['context'] = {'default_partner_id': self.id,
                             'coop_catalog': False, 'coop_section': False}
        return action

    def action_coop_app_hr(self):
        return self._coop_app_action('hr.open_view_employee_list_my', _('Сотрудники'))


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _coop_company_grants(self, user):
        """Приложения организации — по её набору и полномочиям человека.

        CRM здесь заменяет прежнее правило «всем держателям Сделок»: оно
        выдавалось в `res_users.py` этого модуля, а теперь только там, где
        у организации CRM включён.
        """
        grants = super()._coop_company_grants(user)
        memberships = self.env['coop.membership'].sudo().search([
            ('partner_id', '=', user.partner_id.id), ('state', '=', 'active')])
        Groups = self.env['res.groups']
        for membership in memberships:
            org = membership.organization_id
            if not org.is_company or not org.coop_company_id:
                continue
            codes = set(membership.power_ids.mapped('code'))
            for app, (powers, group_xmlid) in APPS.items():
                if org['coop_app_%s' % app] and codes & set(powers):
                    company = org.coop_company_id
                    grants[company] = grants.get(company, Groups) | self.env.ref(group_xmlid)
        return grants

    @api.model
    def _coop_sync_accounting_access(self, organizations=None, users=None):
        """Снять группы приложений, которые человеку больше не положены.

        Общая раздача только добавляет группы — снимает она лишь компании.
        Выключенное приложение без снятия группы оставалось бы открытым
        в другой компании, где оно есть. Администраторов не трогаем.
        """
        super()._coop_sync_accounting_access(organizations, users)
        managed = self.env['res.groups'].union(
            *[self.env.ref(xmlid) for _powers, xmlid in APPS.values()])
        Membership = self.env['coop.membership'].sudo()
        targets = users or self.browse()
        if organizations is not None:
            targets |= Membership.search(
                [('organization_id', 'in', organizations.ids)]).partner_id.sudo().user_ids
        elif not users:
            targets = self.sudo().search([('share', '=', False)])
        for user in targets.sudo():
            if user.has_group('base.group_system'):
                continue
            grants = self._coop_company_grants(user)
            wanted = self.env['res.groups'].union(*grants.values()) if grants else self.env['res.groups']
            extra = (user.group_ids & managed) - wanted
            if extra:
                user.write({'group_ids': [(3, g.id) for g in extra]})
