import re
from json import dumps as json_dumps, loads as json_loads
from werkzeug.urls import url_decode

from odoo.http import request, route
from odoo.http.dispatcher import serialize_exception as _serialize_exception
from odoo.http.stream import content_disposition
from odoo.tools.misc import html_escape
from odoo.tools.safe_eval import safe_eval, time

from odoo.addons.web.controllers.report import ReportController


class DocxReportController(ReportController):
    def _get_docx_report_from_name(self, reportname):
        return request.env["ir.actions.report"]._get_report_from_name(reportname)

    @route()
    def report_routes(self, reportname, docids=None, converter=None, **data):
        """
        Запускает генерацию файла отчета и возвращает его
        """
        report = self._get_docx_report_from_name(reportname)
        # Ветку решаем до разбора `data`: ниже `options` вынимается pop'ом,
        # и штатный контроллер уже не восстановил бы параметры мастера у
        # обычных (qweb) отчётов. Поэтому их отдаём в super() нетронутыми.
        is_docx = converter == "docx" or (
            converter == "pdf" and "docx" in (report.report_type or "")
        )
        if not is_docx:
            return super().report_routes(reportname, docids, converter, **data)

        context = dict(request.env.context)
        _data = dict()
        _docids = [int(i) for i in docids.split(",")] if docids else []
        if data.get("options"):
            _data.update(json_loads(data.pop("options")))
        if data.get("context"):
            # Ignore 'lang' here, because the context in data is the one from the webclient *but* if
            # the user explicitely wants to change the lang, this mechanism overwrites it.
            _data["context"] = json_loads(data["context"])
            if _data["context"].get("lang") and not _data.get("force_context_lang"):
                del _data["context"]["lang"]
            context.update(_data["context"])
        if converter == "docx":
            docx = report.with_context(context)._render_docx_docx(_docids, data=_data)
            docx = docx[0] if isinstance(docx, tuple) else docx
            docxhttpheaders = [
                (
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            ]
            return request.make_response(docx, headers=docxhttpheaders)
        pdf = report.with_context(context)._render_docx_pdf(_docids, data=_data)
        pdf = pdf[0] if isinstance(pdf, tuple) else pdf
        pdfhttpheaders = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf)),
        ]
        return request.make_response(pdf, headers=pdfhttpheaders)

    def _get_docx_filename_pattern(self, report):
        """Выражение имени файла: `object` — запись, без расширения."""
        return report.print_report_name

    def _get_docx_output_filename(self, report, docids, extension):
        filename = "%s.%s" % (report.name, extension)
        pattern = self._get_docx_filename_pattern(report)
        ids = [int(x) for x in docids.split(",") if x.isdigit()] if docids else []
        if not pattern or len(ids) != 1:
            return filename
        obj = request.env[report.model].browse(ids)
        try:
            report_name = safe_eval(pattern, {"object": obj, "time": time})
        except Exception:
            # print_report_name может быть просто именем файла, а не Python-выражением
            report_name = pattern
        if not isinstance(report_name, str) or not report_name.strip():
            return filename
        report_name = re.sub(r"\.(docx?|pdf)$", "", report_name.strip(), flags=re.IGNORECASE)
        return "%s.%s" % (report_name, extension)

    @route()
    def report_download(self, data, context=None, token=None, readonly=True):
        """
        Обрабатывает запрос на скачивание файла отчета
        """
        requestcontent = json_loads(data)
        url, type = requestcontent[0], requestcontent[1]
        try:
            if type in ["docx-docx", "docx-pdf"]:
                converter = "docx" if type == "docx-docx" else "pdf"
                extension = "docx" if type == "docx-docx" else "pdf"

                pattern = "/report/%s/" % ("docx" if type == "docx-docx" else "pdf")
                reportname = url.split(pattern)[1].split("?")[0]

                docids = None
                if "/" in reportname:
                    reportname, docids = reportname.split("/")

                if docids:
                    # Generic report:
                    response = self.report_routes(
                        reportname, docids=docids, converter=converter, context=context
                    )
                else:
                    # Particular report:
                    data = dict(
                        url_decode(url.split("?")[1]).items()
                    ) if "?" in url else {}  # decoding the args represented in JSON
                    if "context" in data:
                        context, data_context = json_loads(context or "{}"), json_loads(
                            data.pop("context")
                        )
                        context = json_dumps({**context, **data_context})
                    response = self.report_routes(
                        reportname, converter=converter, context=context, **data
                    )

                report = self._get_docx_report_from_name(reportname)
                filename = self._get_docx_output_filename(report, docids, extension)
                response.headers.add(
                    "Content-Disposition", content_disposition(filename)
                )
                return response
            else:
                return super(DocxReportController, self).report_download(
                    data, context=context, token=token, readonly=readonly
                )
        except Exception as e:
            se = _serialize_exception(e)
            error = {"code": 200, "message": "Odoo Server Error", "data": se}
            return request.make_response(html_escape(json_dumps(error)))
