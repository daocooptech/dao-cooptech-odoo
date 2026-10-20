from odoo.http import request

from odoo.addons.docx_report_generation.controllers.main import DocxReportController


class DocxTemplateReportController(DocxReportController):
    """Маршруты печати — в docx_report_generation; здесь только имя файла.

    У шаблона из каталога `docx.template` своё выражение имени файла
    (`filename_pattern`); у прочих DOCX-отчётов — `print_report_name`.
    """

    def _get_docx_filename_pattern(self, report):
        template = request.env["docx.template"].sudo().search(
            [("report_id", "=", report.id)], limit=1
        )
        return template.filename_pattern or super()._get_docx_filename_pattern(report)
