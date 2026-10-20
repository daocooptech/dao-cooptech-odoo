from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Квартал параллельной работы: у организации со слоем — кнопки УПД
    # слоя, у остальных — прежняя кнопка l10n_ru_upd_xml. Одна, не две.
    coop_rsbu_enabled = fields.Boolean(related='company_id.rsbu_enabled')
