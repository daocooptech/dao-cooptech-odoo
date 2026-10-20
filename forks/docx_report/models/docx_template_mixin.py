from odoo import models, fields, _


class DocxTemplateMixin(models.AbstractModel):
    _name = "docx.template.mixin"
    _description = "Mixin: DOCX template link"

    docx_template_id = fields.Many2one(
        "docx.template",
        string=_("DOCX шаблон"),
        domain=[("global_template", "=", False)],
        help="DOCX-шаблон, используемый по умолчанию для данного объекта.",
    )
