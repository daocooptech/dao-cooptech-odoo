from odoo import models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _coop_sync_sales_team(self):
        """Отдел продаж организации — её держатели «Сделок».

        Один отдел на компанию учёта. Состав следует за полномочием:
        выдали «Сделки» — человек в отделе, отозвали — вышел. Выключен
        CRM — отдел пустеет: лидов организации никто не ведёт.

        Участников ведём сами, через `crm.team.member` вместе с архивными:
        запись поля `member_ids` движок разбирает только по активным
        участникам и вернувшегося создаёт заново — каждая выкатка
        добавляла по копии на человека (задача 443).
        """
        Team = self.env['crm.team'].sudo()
        Member = self.env['crm.team.member'].sudo().with_context(active_test=False)
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
            users = self.env['res.users']
            if org.coop_app_crm:
                users = Membership.search([
                    ('organization_id', '=', org.id),
                    ('state', '=', 'active'),
                    ('power_ids.code', '=', 'deal'),
                ]).partner_id.user_ids.filtered(
                    # В отдел — только тех, кому компания уже выдана: движок
                    # не пускает в отдел чужой компании, а доступ раздаёт
                    # _coop_sync_accounting_access, и не всегда всем сразу.
                    lambda u: not u.share and company in u.company_ids)
            # По одной записи на человека: старшая остаётся, лишние —
            # в архиве и не оживают.
            keep = {}
            for member in Member.search([('crm_team_id', '=', team.id)], order='id'):
                keep.setdefault(member.user_id.id, member)
            kept = Member.browse([m.id for m in keep.values()])
            wanted = kept.filtered(lambda m: m.user_id in users)
            to_on = wanted.filtered(lambda m: not m.active)
            to_off = Member.search([('crm_team_id', '=', team.id), ('active', '=', True)]) - wanted
            if to_off:
                to_off.active = False
            if to_on:
                to_on.active = True
            missing = users - kept.user_id
            if missing:
                Member.create([{'crm_team_id': team.id, 'user_id': u.id} for u in missing])
