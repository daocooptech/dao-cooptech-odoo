from odoo import Command, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _coop_sync_sales_team(self):
        """Отдел продаж организации — её держатели «Сделок».

        Один отдел на компанию учёта. Состав следует за полномочием:
        выдали «Сделки» — человек в отделе, отозвали — вышел.
        """
        Team = self.env['crm.team'].sudo()
        Membership = self.env['coop.membership'].sudo()
        for org in self.sudo():
            company = org.coop_company_id
            if not company:
                continue
            team = Team.with_context(active_test=False).search(
                [('company_id', '=', company.id)], limit=1)
            if not team:
                team = Team.create({
                    'name': 'Отдел продаж',
                    'company_id': company.id,
                    'use_leads': False,
                    'use_opportunities': True,
                })
            users = Membership.search([
                ('organization_id', '=', org.id),
                ('state', '=', 'active'),
                ('power_ids.code', '=', 'deal'),
            ]).partner_id.user_ids.filtered(
                # В отдел — только тех, кому компания уже выдана: движок
                # не пускает в отдел чужой компании, а доступ раздаёт
                # _coop_sync_accounting_access, и не всегда всем сразу.
                lambda u: not u.share and company in u.company_ids)
            if set(team.member_ids.ids) != set(users.ids):
                team.member_ids = [Command.set(users.ids)]
