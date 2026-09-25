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

    matched_version = fields.Integer(string='Совпала редакция', compute='_compute_result')

    @api.depends('file', 'document_id.fingerprint')
    def _compute_result(self):
        """Сверка идёт по всем редакциям, а не только по последней.

        Владелец 25 сентября 2026 (разбор дисков, п. 1): ответ «не тот
        файл» мало что даёт, если у человека в руках прежняя редакция
        договора. Теперь ответ — «это редакция № 2 от 14 мая».
        """
        Document = self.env['coop.document']
        for record in self:
            mine = Document._fingerprint_of(record.file)
            record.mine_fingerprint = mine
            record.matches = bool(mine) and mine == record.known_fingerprint
            version = record.document_id.sudo().version_ids.filtered(
                lambda v: v.fingerprint == mine)[:1] if mine else False
            record.matched_version = version.number if version else 0
            if not record.file:
                record.verdict = _(
                    '<p class="text-muted">Приложите файл, который у вас '
                    'на руках.</p>')
            elif record.matches:
                record.verdict = _(
                    '<p><b>Тот самый документ.</b> Содержимое вашего файла '
                    'совпадает с тем, что лежит на платформе, до байта.</p>')
            elif version:
                record.verdict = _(
                    '<p><b>Это прежняя редакция — № %(n)s от %(d)s.</b> Файл '
                    'подлинный, но с тех пор документ меняли; действующая — '
                    'последняя редакция на платформе.</p>',
                    n=version.number, d=version.date.strftime('%d.%m.%Y'))
            else:
                record.verdict = _(
                    '<p><b>Это другой файл.</b> Содержимое не совпадает ни с '
                    'одной редакцией на платформе.</p>'
                    '<p>Так бывает не только при подмене: пересохранение '
                    'в другой программе, печать в PDF заново, добавленная '
                    'подпись — всё это меняет содержимое, а значит и '
                    'отпечаток. Сверяйте тот файл, который получили, а не '
                    'его копию.</p>')

    def action_done(self):
        """Итог сверки — в журнал документа (п. 4 разбора)."""
        for record in self.filtered('file'):
            ok = record.matches or record.matched_version
            record.document_id._coop_log(
                'checked_ok' if ok else 'checked_bad',
                note=_('редакция %s', record.matched_version) if record.matched_version
                and not record.matches else False)
        return {'type': 'ir.actions.act_window_close'}
