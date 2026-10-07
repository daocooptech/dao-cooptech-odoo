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

    # Компанию учёта и группу CRM держателям «Сделок» теперь выдаёт
    # набор приложений организации (`org_apps.py`): только там, где CRM
    # у неё включён (решение 450, ответ владельца 08.10.2026).

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
