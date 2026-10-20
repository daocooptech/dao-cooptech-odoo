from odoo import models


class ResCompany(models.Model):
    _inherit = 'res.company'

    def write(self, vals):
        res = super().write(vals)
        if 'rsbu_enabled' in vals:
            # Включили слой — держатели полномочия получают группу РСБУ.
            orgs = self.env['res.partner'].sudo().search(
                [('coop_company_id', 'in', self.ids)])
            if orgs:
                self.env['res.users']._coop_sync_accounting_access(organizations=orgs)
        return res
