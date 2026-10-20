from odoo import fields, models


class DocxCustomField(models.Model):
    _name = "docx.custom.field"
    _description = "Кастомная переменная для DOCX-шаблона"

    report_id = fields.Many2one(
        "ir.actions.report",
        string="DOCX-отчёт",
        required=True,
        ondelete="cascade",
    )

    technical_name = fields.Char(
        string="Техническое имя",
        required=True,
        help="Имя переменной, используемое в шаблоне",
    )

    name = fields.Char(
        string="Название",
        required=True,
        help="Имя для интерфейса.",
    )

    value_python = fields.Text(
        string="Значение (Python)",
        required=True,
        help=(
            "Python-выражение, которое будет вычислено в контексте отчёта.\n"
        ),
    )

    _sql_constraints = [
        (
            "uniq_report_technical_name",
            "unique(report_id, technical_name)",
            "Техническое имя кастомной переменной должно быть уникально в рамках одного отчёта.",
        )
    ]
