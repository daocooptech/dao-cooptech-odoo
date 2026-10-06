# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_FIELDS_MODUL = [
    'module_l10n_ru_act_rev',
    'module_l10n_ru_contract',
    'module_l10n_ru_upd_xml',
    'module_l10n_ru_doc',
    'module_l10n_ru_attorney',
    'module_l10n_ru_advance_payments'
]

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    module_l10n_ru_act_rev = fields.Boolean("Act revise")
    module_l10n_ru_contract = fields.Boolean("Contract")
    module_l10n_ru_upd_xml = fields.Boolean("Report_xml")
    module_l10n_ru_doc = fields.Boolean("Print forms")
    module_l10n_ru_attorney = fields.Boolean("Consent")
    module_l10n_ru_advance_payments = fields.Boolean("Advance payments")

    @api.model
    def write(self, values):
        company = self.env.company
        if company.country_id.code != 'RU':
            if any(field in values for field in _FIELDS_MODUL):
                raise UserError("Признак Российской компании не обнаружен!")
        if _FIELDS_MODUL:
            missing_modules = set()
            for field in _FIELDS_MODUL:
                if self.mapped(field)[0]:
                    module_name = field[7:]
                    module_installed = self.env['ir.module.module'].search([('name', '=', module_name)], limit=1)
                    if not module_installed:
                        missing_modules.add(module_name)
            if missing_modules:
                message = "Обратитесь в тех.поддержку для получения лицензии для следующих модулей:\n" + \
                      "\n".join(missing_modules)
                raise UserError(message)
        return super(ResConfigSettings, self).write(values)
