import re
import zipfile
from base64 import b64decode
from io import BytesIO
from logging import getLogger

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = getLogger(__name__)


class DocxTemplate(models.Model):
    """
    Высокоуровневый DOCX-шаблон договора.

    Все технические поля (name, report_type, model,
    report_docx_template, print_report_name и т.д.)
    берём напрямую из ir.actions.report через _inherits.
    """
    _name = "docx.template"
    _description = "DOCX-шаблон договора"
    _inherits = {"ir.actions.report": "report_id"}

    report_id = fields.Many2one(
        "ir.actions.report",
        string="Действие отчёта",
        required=True,
        ondelete="cascade",
    )

    filename_pattern = fields.Char(
        string="Шаблон имени файла",
        help=(
            "Python-выражение, вычисляемое при скачивании DOCX.\n"
            "Должно вернуть строку БЕЗ расширения.\n"
            "Доступные переменные:\n"
            " - object: запись, для которой печатается отчёт\n"
            " - time: модуль time из Python"
        ),
    )

    docx_output_type = fields.Selection(
        selection=[
            ("docx", "DOCX"),
        ],
        string="Формат вывода",
        default="docx",
        required=True,
    )

    docx_model_id = fields.Many2one(
        "ir.model",
        string="Модель документа",
        ondelete="set null"
    )

    available_field_ids = fields.Many2many(
        "ir.model.fields",
        string="Доступные поля (подсказка)",
        compute="_compute_available_field_ids",
        readonly=True,
    )

    global_template = fields.Boolean(
        string="Глобальный",
        default=True,
        help="Если включено, шаблон доступен глобально",
    )

    report_docx_template_filename = fields.Char(
        string="Имя файла шаблона",
        help="Имя загруженного DOCX-шаблона. Не влияет на имя выводимого файла.",
    )

    hint_model_id = fields.Many2one(
        "ir.model",
        string="Модель для подсказки полей",
        help=(
            "Используется только как подсказка при создании шаблона.\n"
            "На реальную модель отчёта не влияет."
        ),
    )

    def action_bind_to_actions(self):
        """Создать contextual action (binding) для каждого шаблона."""
        for template in self:
            template.report_id.create_action()
        return True

    def action_bind_all_to_actions(self):
        """Добавить в печать действия все шаблоны сразу."""
        templates = self.search([])
        for template in templates:
            template.report_id.create_action()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Готово"),
                "message": _("Все шаблоны (%d) добавлены в действия печати.") % len(templates),
                "type": "success",
                "sticky": False,
            },
        }

    def action_unbind_from_actions(self):
        """Удалить contextual action (binding) для каждого шаблона."""
        for template in self:
            template.report_id.unlink_action()
        return True


    @api.depends("hint_model_id", "docx_model_id")
    def _compute_available_field_ids(self):
        """
        Это всего лишь подсказка для конструктора шаблонов.

        Берём поля:
        - в первую очередь для hint_model_id
        - если hint_model_id не задана — для docx_model_id
        """
        Fields = self.env["ir.model.fields"]
        for rec in self:
            model_rec = rec.hint_model_id or rec.docx_model_id
            if model_rec:
                rec.available_field_ids = Fields.search(
                    [("model_id", "=", model_rec.id)],
                    order="name",
                )
            else:
                rec.available_field_ids = Fields.browse()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Формат по умолчанию тоже задаёт тип: иначе шаблон, созданный
            # без явного формата (из кода, из данных), остаётся qweb-pdf.
            output_type = vals.setdefault("docx_output_type", "docx")
            if output_type and not vals.get("report_type"):
                if output_type == "docx":
                    vals["report_type"] = "docx-docx"
                elif output_type == "pdf":
                    vals["report_type"] = "docx-pdf"
                elif output_type == "docx_pdf":
                    vals["report_type"] = "docx-docx"

            model_id = vals.get("docx_model_id")
            if model_id and not vals.get("model"):
                model_rec = self.env["ir.model"].browse(model_id)
                vals["model"] = model_rec.model or False

        return super().create(vals_list)

    def write(self, vals):
        if "docx_output_type" in vals and "report_type" not in vals:
            out = vals["docx_output_type"]
            if out == "docx":
                vals["report_type"] = "docx-docx"
            elif out == "pdf":
                vals["report_type"] = "docx-pdf"
            elif out == "docx_pdf":
                vals["report_type"] = "docx-docx"

        if "docx_model_id" in vals and "model" not in vals:
            model_rec = self.env["ir.model"].browse(vals["docx_model_id"])
            vals["model"] = model_rec.model or False
        return super().write(vals)

    def action_validate_docx_template(self):
        self.ensure_one()
        _logger.info("[DOCX VALIDATION] --- START ---")

        if not self.report_docx_template:
            raise UserError(_("Не загружен DOCX-шаблон."))
        if not self.docx_model_id:
            raise UserError(_("Заполните поле 'Модель документа'."))

        try:
            # Odoo 20: Binary-поле отдаёт BinaryValue (сырые байты), а не base64.
            tpl = self.report_docx_template
            raw = tpl.content if hasattr(tpl, "content") else b64decode(tpl)
            zf = zipfile.ZipFile(BytesIO(raw))
        except Exception as e:
            raise UserError(_("Файл шаблона повреждён или не является DOCX: %s") % e)

        pattern = re.compile(r"{{\s*(.*?)\s*}}", re.DOTALL)
        tag_pattern = re.compile(r"<[^>]+>")
        loop_pattern = re.compile(
            r"{%\s*for\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+in\s+.*?%}", re.DOTALL
        )

        expressions = set()
        loop_var_names = set()

        for name in zf.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            xml = zf.read(name).decode("utf-8", errors="ignore")

            for match in pattern.finditer(xml):
                expr = match.group(1)
                expr = tag_pattern.sub("", expr)
                expr = expr.strip()
                if expr:
                    expressions.add(expr)

            for m in loop_pattern.finditer(xml):
                var_name = m.group(1)
                loop_var_names.add(var_name)

        if not expressions:
            return self._validation_notification(
                _("В шаблоне не найдено ни одной переменной {{ }}."), "info"
            )

        allowed_roots = {
            "env", "model", "record", "records", "docs", "user",
            "res_company", "website", "web_base_url", "time",
            "context_timestamp", "UserError", "Warning", "format_number",
        }

        root_model_map = {
            "record": self.docx_model_id.model,
            "records": self.docx_model_id.model,
            "docs": self.docx_model_id.model,
            "user": "res.users",
            "res_company": "res.company",
        }

        custom_var_names = (
            set(self.docx_custom_field_ids.mapped("technical_name"))
            if hasattr(self, "docx_custom_field_ids")
            else set()
        )

        relational_types = {"many2one", "one2many", "many2many"}
        missing = set()


        func_stop_patterns = ("mapped", "filtered", "sorted", "search")

        for expr in expressions:
            core = expr.split("|", 1)[0]
            for sep in (" if ", " or ", " and ", " else "):
                core = core.split(sep, 1)[0]
            core = core.strip()

            for func in func_stop_patterns:
                core = re.split(rf"\.{func}\s*\(", core)[0]

            if not core:
                continue

            match = re.search(r'[a-zA-Z_][a-zA-Z0-9_.\[\]\'\"]*', core)
            if not match:
                continue

            token = match.group(0)

            token = re.sub(r"\['([^']+)']", r".\1", token)
            token = re.sub(r'\["([^"]+)"]', r".\1", token)

            parts = token.split(".")
            root = parts[0]

            if root in custom_var_names and root not in allowed_roots:
                continue
            if root in loop_var_names and root not in allowed_roots and root not in custom_var_names:
                continue
            if root not in allowed_roots:
                missing.add(root)
                continue

            model_name = root_model_map.get(root)

            if not model_name:
                continue

            current_model = self.env[model_name]

            path = root

            for name in parts[1:]:
                name_stripped = name.strip()

                if any(
                        name_stripped.startswith(f"{func}(") or name_stripped == func
                        for func in func_stop_patterns
                ):
                    break

                if current_model is None:
                    break

                field = current_model._fields.get(name_stripped)
                if not field:
                    _logger.warning(
                        "[DOCX VALIDATION] MISSING field: %s.%s (model=%s). "
                        "Available fields: %s",
                        path,
                        name_stripped,
                        current_model._name,
                        ", ".join(sorted(current_model._fields.keys())),
                    )
                    missing.add(f"{path}.{name_stripped}")
                    break

                path = f"{path}.{name_stripped}"

                if field.type in relational_types and field.comodel_name:
                    _logger.info(
                        "[DOCX VALIDATION] Following relation → %s", field.comodel_name
                    )
                    current_model = self.env[field.comodel_name]
                else:
                    current_model = None

        _logger.info("[DOCX VALIDATION] ----- END CHECK -----")

        if missing:
            _logger.warning("[DOCX VALIDATION] Missing vars: %s", missing)
            text = "\n".join(sorted(missing))
            raise UserError(
                _("Обнаружены неизвестные переменные или поля в шаблоне для модели '%s':\n%s")
                % (self.docx_model_id.model, text)
            )

        return self._validation_notification(
            _("Все переменные в шаблоне валидны для модели %s.") % self.docx_model_id.model,
            "success",
        )

    def _validation_notification(self, message, type="success"):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Валидация DOCX-шаблона"),
                "message": message,
                "type": type,
                "sticky": False,
            },
        }
