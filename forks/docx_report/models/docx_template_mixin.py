from odoo import fields, models


class DocxTemplateMixin(models.AbstractModel):
    _name = "docx.template.mixin"
    _description = "Mixin: DOCX template link"

    docx_template_id = fields.Many2one(
        "docx.template",
        string="DOCX шаблон",
        domain=[("global_template", "=", False)],
        help="DOCX-шаблон, используемый по умолчанию для данного объекта.",
    )
