from odoo import models, fields, api
import os

class ReportTemplate(models.Model):
    _name = 'contract.report.template'
    _description = 'Шаблоны отчетов'

    name = fields.Char(string='Название', required=True)
    attachment = fields.Binary(string='Файл шаблона', required=True)
    attachment_filename = fields.Char(string='Имя файла')
    typeformat = fields.Char(string='Формат', compute='_compute_format', store=True)
    create_date = fields.Datetime(string='Дата создания', default=fields.Datetime.now)

    @api.depends('attachment_filename')
    def _compute_typeformat(self):
        for rec in self:
            if rec.attachment_filename:
                rec.typeformat = os.path.splitext(rec.attachment_filename)[1].lstrip('.').lower()
            else:
                rec.typeformat = False