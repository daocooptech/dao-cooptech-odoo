from json import dumps as json_dumps, loads as json_loads
from werkzeug.urls import url_decode
import re

from odoo.http import (
    content_disposition,
    request,
    route,
    serialize_exception as _serialize_exception,
)
from odoo.tools import html_escape
from odoo.tools.safe_eval import safe_eval, time

from odoo.addons.web.controllers.report import ReportController

import logging
_logger = logging.getLogger(__name__)

class DocxReportController(ReportController):

    def _prepare_docx_report_context(self, docids, data):
        """
        По сути дублирует сбор контекста и docids в части базового report_routes. Новая логика непосредственно в переопределенном report_routes.
        Возможно есть и более изящный способ.
        """
        context = dict(request.env.context)
        payload = {}
        docids_list = [int(i) for i in docids.split(",")] if docids else []
        if data.get("options"):
            payload.update(json_loads(data.pop("options")))
        if data.get("context"):
            payload["context"] = json_loads(data["context"])
            if payload["context"].get("lang") and not payload.get("force_context_lang"):
                del payload["context"]["lang"]
            context.update(payload["context"])
        return context, payload, docids_list

    def _get_docx_report_from_name(self, reportname):
        template = request.env["docx.template"].search([("report_name", "=", reportname)], limit=1)
        if template:
            return template.report_id
        return request.env["ir.actions.report"]._get_report_from_name(reportname)

    @route()
    def report_routes(self, reportname, docids=None, converter=None, **data):
        """
        Расширенный маршрут `/report/<converter>/<reportname>/<docids>`
        Добавлена поддержка:
            - converter=docx  → генерация DOCX
            - converter=pdf   → конвертация DOCX → PDF (Gotenberg)
        """
        _logger.info("[ROUTE] report_routes() called: reportname=%s converter=%s docids=%s",
                     reportname, converter, docids)

        report = self._get_docx_report_from_name(reportname)

        # Решаем ветку ДО того как трогать `data`: _prepare_docx_report_context()
        # делает деструктивный data.pop("options"), после чего штатный
        # ReportController уже не сможет восстановить data['form']/'context' для
        # не-docx (qweb-pdf) отчётов. Поэтому для не-docx отчётов прозрачно
        # отдаём управление в super() с нетронутым оригинальным **data.
        is_docx = converter == "docx" or (
            converter == "pdf" and "docx" in (report.report_type or "")
        )
        if not is_docx:
            return super().report_routes(
                reportname, docids, converter, **data
            )

        context, payload, docids_list = self._prepare_docx_report_context(docids, data)

        # -----------------------
        # 1) DOCX генерация
        # -----------------------
        if converter == "docx":
            _logger.info("[ROUTE] DOCX branch for report=%s", reportname)

            docx_result = report.with_context(context)._render_docx_docx(
                docids_list, data=payload
            )
            # _render_docx_docx returns (bytes, "docx") tuple
            docx_bytes = docx_result[0] if isinstance(docx_result, tuple) else docx_result
            headers = [
                (
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            ]
            return request.make_response(docx_bytes, headers=headers)

        # -----------------------
        # 2) PDF генерация из DOCX
        # -----------------------
        _logger.info("[ROUTE] PDF branch for report=%s docids=%s", reportname, docids_list)

        pdf_result = report.with_context(context)._render_docx_pdf(
            docids_list, data=payload
        )

        # Может быть либо bytes, либо (bytes, ext)
        if isinstance(pdf_result, tuple):
            pdf_content = pdf_result[0]
        else:
            pdf_content = pdf_result

        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf_content)),
        ]
        return request.make_response(pdf_content, headers=headers)

    def _get_docx_output_filename(self, report, docids, extension):
        """
        Возвращает финальное имя файла для скачивания DOCX.

        Приоритет:
        1) docx.template.filename_pattern (если существует docx.template)
        2) report.print_report_name (как fallback, если оно всё же задано)
        3) report.name

        Ожидается, что выражение возвращает строку БЕЗ расширения (.docx).
        """
        filename = "%s.%s" % (report.name, extension)

        template = request.env["docx.template"].sudo().search(
            [("report_id", "=", report.id)], limit=1
        )

        pattern = None
        if template and template.filename_pattern:
            pattern = template.filename_pattern
        elif report.print_report_name:
            pattern = report.print_report_name

        if not pattern or not docids:
            return filename

        ids = [int(x) for x in docids.split(",") if x.isdigit()]
        if len(ids) != 1:
            return filename

        obj = request.env[report.model].browse(ids)

        try:
            report_name = safe_eval(
                pattern,
                {"object": obj, "time": time},
            )
        except Exception:
            return filename

        if not isinstance(report_name, str):
            return filename

        clean = report_name.strip()
        if not clean:
            return filename

        clean = re.sub(r"\.(docx?|pdf)$", "", clean, flags=re.IGNORECASE)

        return "%s.%s" % (clean, extension)

    @route()
    def report_download(self, data, context=None, token=None, readonly=True):
        """
        Обрабатывает запрос на скачивание файла отчета.
        Расширен для:
          - docx-docx  (DOCX)
          - docx-pdf   (PDF из DOCX)
        """
        _logger.info("[REPORT DOWNLOAD] data=%s, token=%s", data, token)

        requestcontent = json_loads(data)
        url, type_ = requestcontent[0], requestcontent[1]

        try:
            if type_ in ["docx-docx", "docx-pdf"]:
                converter = "docx" if type_ == "docx-docx" else "pdf"
                extension = "docx" if type_ == "docx-docx" else "pdf"

                pattern = "/report/%s/" % ("docx" if type_ == "docx-docx" else "pdf")
                reportname = url.split(pattern)[1].split("?")[0]

                docids = None
                if "/" in reportname:
                    reportname, docids = reportname.split("/")

                _logger.info(
                    "[REPORT DOWNLOAD] type=%s converter=%s extension=%s reportname=%s docids=%s",
                    type_, converter, extension, reportname, docids,
                )

                if docids:
                    response = self.report_routes(
                        reportname, docids=docids, converter=converter, context=context
                    )

                else:
                    query_data = {}
                    if "?" in url:
                        query_data = dict(url_decode(url.split("?")[1]).items())

                    if "context" in query_data:
                        base_ctx = json_loads(context or "{}") if context else {}
                        data_context = json_loads(query_data.pop("context"))
                        context = json_dumps({**base_ctx, **data_context})

                    response = self.report_routes(
                        reportname, converter=converter, context=context, **query_data
                    )

                report = self._get_docx_report_from_name(reportname)
                filename = self._get_docx_output_filename(report, docids, extension)

                response.headers.add(
                    "Content-Disposition", content_disposition(filename)
                )
                return response

            else:
                return super().report_download(
                    data, context=context, token=token, readonly=readonly
                )

        except Exception as e:
            _logger.exception("[REPORT DOWNLOAD] ERROR: %s", e)
            se = _serialize_exception(e)
            error = {"code": 200, "message": "Odoo Server Error", "data": se}
            return request.make_response(html_escape(json_dumps(error)))
