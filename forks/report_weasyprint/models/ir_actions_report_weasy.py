import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

try:
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration
except Exception as e:
    HTML = None
    FontConfiguration = None
    _logger.warning("WeasyPrint not available: %s", e)


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    use_weasyprint = fields.Boolean(
        string="Render with WeasyPrint",
        help="Render this PDF report using WeasyPrint instead of wkhtmltopdf."
    )

    def _weasyprint_enabled_for(self, report):
        if not (HTML and FontConfiguration and report):
            return False

        ctx = self.env.context
        if ctx.get("report_force_wkhtml"):
            return False
        if ctx.get("report_force_weasy"):
            return True

        return bool(report.use_weasyprint)

    @api.model
    def _run_wkhtmltopdf(
        self,
        bodies,
        report_ref=False,
        header=None,
        footer=None,
        landscape=False,
        specific_paperformat_args=None,
        set_viewport_size=False,
    ):
        report = None
        if report_ref:
            try:
                report = self._get_report(report_ref)
            except Exception:
                report = None

        if not self._weasyprint_enabled_for(report):
            return super()._run_wkhtmltopdf(
                bodies,
                report_ref=report_ref,
                header=header,
                footer=footer,
                landscape=landscape,
                specific_paperformat_args=specific_paperformat_args,
                set_viewport_size=set_viewport_size,
            )

        html = "".join(bodies)

        base_url = (
            self.env["ir.config_parameter"].sudo().get_str("report.url")
            or self.env["ir.config_parameter"].sudo().get_str("web.base.url")
            or ""
        )

        font_config = FontConfiguration()
        pdf_bytes = HTML(
            string=html,
            base_url=base_url,
        ).write_pdf(font_config=font_config)

        return pdf_bytes
