from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _coop_deal_orgs(self, user):
        """Организации, где у человека полномочие «Сделки»."""
        memberships = self.env['coop.membership'].sudo().search([
            ('partner_id', '=', user.partner_id.id),
            ('state', '=', 'active'),
            ('power_ids.code', '=', 'deal'),
        ])
        return memberships.organization_id.filtered('is_company')

    @api.model
    def _coop_company_grants(self, user):
        """CRM — по полномочию «Сделки» (решение 450).

        Держатель «Сделок» получает компанию учёта своей организации и
        группу «все лиды отдела»: видит и ведёт лиды всей организации, а не
        только свои. Группы бухгалтерии отсюда не приходят.
        """
        grants = super()._coop_company_grants(user)
        group = self.env.ref('sales_team.group_sale_salesman_all_leads')
        for org in self._coop_deal_orgs(user):
            if org.coop_company_id:
                grants[org.coop_company_id] = grants.get(
                    org.coop_company_id, self.env['res.groups']) | group
        return grants

    @api.model
    def _coop_sync_accounting_access(self, organizations=None, users=None):
        super()._coop_sync_accounting_access(organizations, users)
        if organizations is None and users:
            # Пересчитаны отдельные люди — и отделы только их организаций.
            organizations = self.env['coop.membership'].sudo().search(
                [('partner_id', 'in', users.partner_id.ids)]).organization_id
        orgs = organizations if organizations is not None else \
            self.env['res.partner'].sudo().search([('coop_company_id', '!=', False)])
        orgs.filtered('coop_company_id')._coop_sync_sales_team()
