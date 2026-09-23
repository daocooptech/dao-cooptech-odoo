# -*- coding: utf-8 -*-
"""Сверка своего экземпляра с тем, что лежит на платформе.

Человек грузит файл, который у него на руках, и видит ответ на один
вопрос: тот ли это документ.

Ответ даётся словами, а не «true/false»: «совпал» и «разошёлся» — разные
новости, и вторая требует объяснения, что делать дальше.
"""
from odoo import _, api, fields, models


class CoopDocumentCheck(models.TransientModel):
    _name = 'coop.document.check'
    _description = 'Сверка экземпляра документа'

    document_id = fields.Many2one(
        'coop.document', string='Документ', required=True, readonly=True)
    known_fingerprint = fields.Char(
        related='document_id.fingerprint', string='Отпечаток на платформе',
        readonly=True)

    file = fields.Binary(string='Ваш экземпляр')
    file_name = fields.Char(string='Имя файла')

    mine_fingerprint = fields.Char(
        string='Отпечаток вашего файла', compute='_compute_result')
    matches = fields.Boolean(string='Совпало', compute='_compute_result')
    verdict = fields.Html(string='Итог', compute='_compute_result')

    @api.depends('file', 'document_id.fingerprint')
    def _compute_result(self):
        Document = self.env['coop.document']
        for record in self:
            mine = Document._fingerprint_of(record.file)
            record.mine_fingerprint = mine
            record.matches = bool(mine) and mine == record.known_fingerprint
            if not record.file:
                record.verdict = _(
                    '<p class="text-muted">Приложите файл, который у вас '
                    'на руках.</p>')
            elif record.matches:
                record.verdict = _(
                    '<p><b>Тот самый документ.</b> Содержимое вашего файла '
                    'совпадает с тем, что лежит на платформе, до байта.</p>')
            else:
                record.verdict = _(
                    '<p><b>Это другой файл.</b> Содержимое не совпадает с '
                    'тем, что лежит на платформе.</p>'
                    '<p>Так бывает не только при подмене: пересохранение '
                    'в другой программе, печать в PDF заново, добавленная '
                    'подпись — всё это меняет содержимое, а значит и '
                    'отпечаток. Сверяйте тот файл, который получили, а не '
                    'его копию.</p>')
