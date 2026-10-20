from odoo import models, api


class IrModel(models.Model):
    _inherit = "ir.model"

    @api.depends('model', 'name')
    def _compute_display_name(self):
        super()._compute_display_name()

        if self.env.context.get('from_docx_template'):
            for record in self:
                record.display_name = record.model or record.name