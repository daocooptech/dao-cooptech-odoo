from odoo import api, models


class CoopMembership(models.Model):
    _inherit = 'coop.membership'

    # Доступ к компании учёта следует за полномочием: выдали «Бухгалтерию
    # и счета» — компания появилась у человека в списке, отозвали или
    # членство закончилось — пропала.

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._coop_sync_accounting()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'power_ids', 'state', 'partner_id', 'organization_id'} & set(vals):
            self._coop_sync_accounting()
        return result

    def unlink(self):
        users = self.filtered('organization_id.coop_company_id').partner_id.sudo().user_ids
        result = super().unlink()
        if users:
            self.env['res.users']._coop_sync_accounting_access(users=users)
        return result

    def _coop_sync_accounting(self):
        organizations = self.organization_id.filtered('coop_company_id')
        if organizations:
            self.env['res.users']._coop_sync_accounting_access(organizations)
