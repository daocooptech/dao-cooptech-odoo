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
        group = self.env.ref('account.group_account_invoice')
        # Список организаций с полномочием считается без зависимости от
        # членства (coop_base): в той же транзакции, где полномочие только
        # что сняли, он отдал бы прежнее значение, и компания осталась бы.
        users.sudo().invalidate_recordset(['coop_treasury_partner_ids'])
        for user in users.sudo():
            treasury = user.coop_treasury_partner_ids - user.partner_id
            granted = treasury.coop_company_id
            wanted = (user.company_ids - coop_companies) | granted
            vals = {}
            if wanted != user.company_ids:
                vals['company_ids'] = [Command.set(wanted.ids)]
                # Основная компания должна остаться среди разрешённых,
                # иначе движок запись не примет.
                if user.company_id not in wanted:
                    vals['company_id'] = (wanted - coop_companies)[:1].id
            if granted and group not in user.group_ids:
                vals['group_ids'] = [Command.link(group.id)]
            if vals:
                user.write(vals)
