from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _coop_company_grants(self, user):
        """Держателю «Бухгалтерии и счетов» организации со слоем — РСБУ.

        Решение 449: учёт и УПД организации ведёт тот, кому она выдала
        полномочие. Правила записей слоя ограничивают его компаниями учёта
        его организаций.
        """
        grants = super()._coop_company_grants(user)
        group = self.env.ref('rsbu_journal.group_rsbu_journal_manager')
        for org in (user.coop_treasury_partner_ids - user.partner_id):
            company = org.coop_company_id
            if company and company.rsbu_enabled:
                grants[company] = grants.get(company, self.env['res.groups']) | group
        return grants
