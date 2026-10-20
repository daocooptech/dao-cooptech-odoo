from odoo import api, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        """Новой компании — типовой план 94н сразу, как при установке модуля.

        В пуле организации заводятся всё время, а мастер загрузки берёт
        компанию по умолчанию — компанию платформы.
        """
        companies = super().create(vals_list)
        Wizard = self.env['rsbu.account.load.wizard'].sudo()
        for company in companies:
            Wizard.create({'company_id': company.id}).action_load()
        return companies
