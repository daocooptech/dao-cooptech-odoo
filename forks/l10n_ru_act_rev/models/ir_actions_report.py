from odoo import api, models


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    @api.model
    def _prepare_account_financial_report_context(self, data):
        lang = data and data.get("account_financial_report_lang") or ""
        return dict(self.env.context or {}, lang=lang) if lang else False
