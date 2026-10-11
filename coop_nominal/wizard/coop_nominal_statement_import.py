# -*- coding: utf-8 -*-
from odoo import fields, models


class CoopNominalStatementImport(models.TransientModel):
    _name = 'coop.nominal.statement.import'
    _description = 'Загрузка выписки по номинальному счёту'

    account_id = fields.Many2one(
        'coop.nominal.account', string='Счёт', required=True)
    file = fields.Binary(string='Файл выписки 1С', required=True)
    file_name = fields.Char(string='Имя файла')

    def action_import(self):
        self.ensure_one()
        statement = self.account_id._import_statement(
            self.file.content, self.file_name)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'coop.nominal.statement',
            'res_id': statement.id,
            'view_mode': 'form',
        }
