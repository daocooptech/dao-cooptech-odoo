import base64
from odoo import models, fields, api
from io import BytesIO

try:
    from docxtpl import DocxTemplate
except ImportError:
    DocxTemplate = None

class ReportTemplateWizard(models.TransientModel):
    _name = 'report.template.wizard'
    _description = 'Визард выбора шаблона для печати договора'

    contract_id = fields.Many2one('model.contract', string='Договор', required=True)
    typeformat = fields.Selection([('docx','DOCX'),
                                   ('md','MD')
                                   ], string='Формат', required=True)
    template_id = fields.Many2one('contract.report.template', string='Шаблон отчета', required=True)
    generated_report = fields.Binary(string='Сформированный отчет')

    def print_report(self):
        self.ensure_one()
        template = self.template_id
        contract = self.contract_id

        if template.format == 'docx':
            template_data = base64.b64decode(template.attachment)
            docx_io = BytesIO(template_data)
            doc = DocxTemplate(docx_io)

            context = {
                'o': contract,
                'user': self.env.user,
                'name': contract.name or '',
            }
            doc.render(context)

            output_io = BytesIO()
            doc.save(output_io)
            output_io.seek(0)

            self.generated_report = base64.b64encode(output_io.read())
            self.report_filename = f'{contract.name or "report"}.docx'

            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/?model={self._name}&id={self.id}&field=generated_report&filename={self.report_filename}&download=true',
                'target': 'self',
            }

        elif template.format == 'md':
            md_content = f"# Отчет по договору\n\nНазвание договора: {contract.name or ''}\n"
            self.generated_report = base64.b64encode(md_content.encode('utf-8'))
            self.report_filename = f'{contract.name or "report"}.md'

            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/?model={self._name}&id={self.id}&field=generated_report&filename={self.report_filename}&download=true',
                'target': 'self',
            }

        else:
            raise UserError('Неподдерживаемый формат шаблона')