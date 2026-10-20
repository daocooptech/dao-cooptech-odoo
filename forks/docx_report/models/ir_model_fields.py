from odoo import api, fields, models


class IrModelFields(models.Model):
    _inherit = "ir.model.fields"

    docx_type_label = fields.Char(
        string="Тип для DOCX",
        compute="_compute_docx_type_label",
        readonly=True,
    )

    @api.depends("ttype", "relation", "selection_ids.value")
    def _compute_docx_type_label(self):
        for field in self:
            t = field.ttype or ""
            if field.relation and field.ttype in ("many2one", "one2many", "many2many"):
                t = f"{field.ttype} ({field.relation})"

            elif field.ttype == "selection":
                values = field.selection_ids.mapped("value")
                if values:
                    t = f"selection ({', '.join(values)})"
                else:
                    t = "selection"
            field.docx_type_label = t
