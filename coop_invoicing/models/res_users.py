from odoo import Command, api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _coop_sync_accounting_access(self, organizations=None, users=None):
        """Дать и снять доступ к компаниям учёта по полномочию.

        Решение 449: счета и УПД организации видит и выставляет тот, кому
        она выдала «Бухгалтерию и счета». Остальные её члены видят сделку и
        акт, а компании учёта у них в списке нет.

        `organizations` — чьих членов пересчитать, `users` — кого именно;
        без обоих — всех внутренних пользователей.
        """
        Membership = self.env['coop.membership'].sudo()
        coop_companies = self.env['res.partner'].sudo().search(
            [('coop_company_id', '!=', False)]).coop_company_id
        if not coop_companies:
            return
        users = users or self.browse()
        if organizations is not None:
            users |= Membership.search(
                [('organization_id', 'in', organizations.ids)]).partner_id.sudo().user_ids
        elif not users:
            users = self.sudo().search([('share', '=', False)])
        # Список организаций с полномочием считается без зависимости от
        # членства (coop_base): в той же транзакции, где полномочие только
        # что сняли, он отдал бы прежнее значение, и компания осталась бы.
        users.sudo().invalidate_recordset(['coop_treasury_partner_ids'])
        for user in users.sudo():
            grants = self._coop_company_grants(user)
            granted = self.env['res.company'].browse([c.id for c in grants])
            groups = self.env['res.groups'].union(*grants.values()) if grants else self.env['res.groups']
            wanted = (user.company_ids - coop_companies) | granted
            vals = {}
            if wanted != user.company_ids:
                vals['company_ids'] = [Command.set(wanted.ids)]
                # Основная компания должна остаться среди разрешённых,
                # иначе движок запись не примет.
                if user.company_id not in wanted:
                    vals['company_id'] = (wanted - coop_companies)[:1].id
            missing = groups - user.group_ids
            if missing:
                vals['group_ids'] = [Command.link(g.id) for g in missing]
            if vals:
                user.write(vals)

    @api.model
    def _coop_company_grants(self, user):
        """Какие компании учёта положены человеку и какие группы при них.

        Здесь — бухгалтерия: держатель «Бухгалтерии и счетов» получает
        компанию своей организации и группу «Счета». Другие модули
        добавляют своё (CRM — по полномочию «Сделки») и зовут super().
        Возвращает {компания: группы}.
        """
        group = self.env.ref('account.group_account_invoice')
        grants = {}
        for org in (user.coop_treasury_partner_ids - user.partner_id):
            if org.coop_company_id:
                grants[org.coop_company_id] = grants.get(org.coop_company_id, self.env['res.groups']) | group
        return grants
