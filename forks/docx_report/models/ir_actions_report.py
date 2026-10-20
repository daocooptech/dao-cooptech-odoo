from base64 import b64decode
from io import BytesIO
from logging import getLogger

from docxtpl import DocxTemplate

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval, time

_logger = getLogger(__name__)


class IrActionsReport(models.Model):
    """Разница с docx_report_generation: кастомные переменные и запись как есть.

    Тип отчёта `docx-docx`, поле шаблона, имя отчёта, вложения и склейка
    живут в docx_report_generation. Здесь рендер отдаёт в шаблон запись
    целиком (`record`, `docs`), а не словарь её полей: шаблоны УПД и
    договора выпуска ходят по связям (`docs.partner_id.vat`), и к ним
    добавляются вычисляемые переменные отчёта.
    """

    _inherit = "ir.actions.report"

    docx_custom_field_ids = fields.One2many(
        "docx.custom.field",
        "report_id",
        string="Кастомные переменные DOCX",
    )

    def _render_docx_template(self, template, values=None):
        self.ensure_one()
        if values is None:
            values = {}
        user = self.env["res.users"].browse(self.env.uid)
        website = None
        # Odoo 20: request.website убран, текущий сайт — env.website.
        if "website" in self.env and self.env.website:
            website = self.env.website
        values.update(
            record=values["docs"],
            time=time,
            context_timestamp=lambda t: fields.Datetime.context_timestamp(
                self.with_context(tz=user.tz), t
            ),
            user=user,
            res_company=user.company_id,
            website=website,
            web_base_url=self.env["ir.config_parameter"]
            .sudo()
            .get_str("web.base.url", default=""),
        )

        record = values.get("record")
        eval_context = {
            "env": self.env,
            "user": user,
            "record": record,
            "docs": record,
            "time": time,
            "context": self.env.context,
        }
        for custom in self.docx_custom_field_ids:
            tech = (custom.technical_name or "").strip()
            if not tech:
                continue
            try:
                values[tech] = safe_eval(custom.value_python or "", eval_context)
            except Exception as e:
                raise UserError(
                    _("Ошибка при вычислении кастомной переменной «%(name)s»: %(error)s",
                      name=tech, error=e)
                ) from e

        docx_content = BytesIO()
        # Odoo 20: Binary-поле отдаёт BinaryValue (сырые байты), а не base64.
        template_bytes = (
            template.content if hasattr(template, "content") else b64decode(template)
        )
        with BytesIO(template_bytes) as template_file:
            doc = DocxTemplate(template_file)
            doc.render(values)
            doc.save(docx_content)
        docx_content.seek(0)
        return docx_content
