# -*- coding: utf-8 -*-
"""Данные старого УПД, которые переживут снятие `l10n_ru_upd_xml` (задача 294, К1).

rudoo уводит УПД на РСБУ-слой, а `l10n_ru_upd_xml` объявлен устаревшим.
Когда модуль снимут, Odoo удалит колонки полей, объявленных только им, —
ID участников ЭДО, код оператора, дом и офис, код ФИАС, ОКЕИ. Здесь они
объявлены повторно с тем же описанием: колонка остаётся за этим модулем.

И второе: старый модуль XML УПД не хранит, а собирает при каждом запросе.
Выданный документ после перехода собрать заново нельзя — номер файла
(`ИдФайл`) и реквизиты уже другие. Поэтому до перехода каждый выданный
УПД сохраняется вложением к счёту под прежним `ИдФайл` (решение владельца
20.10.2026: учёт в слое с 01.01.2027; хранить не меньше пяти лет —
ст. 29 402-ФЗ, разбор бухгалтера).
"""
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

UPD_REPORT = 'l10n_ru_upd_xml.demo_report_xml_view'
ARCHIVE_NOTE = 'УПД, выданный до перехода на РСБУ-слой'


class ResCompany(models.Model):
    _inherit = 'res.company'

    edi = fields.Char(string='ID EDI', readonly=False)
    edi_operator = fields.Char(string='Код оператора ЭДО', size=3, default='2BM')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    edi = fields.Char('ID EDI')
    house = fields.Char('Дом')
    office = fields.Char('Квартира, офис')
    fias_id = fields.Char('Код ФИАС')


class UomUom(models.Model):
    _inherit = 'uom.uom'

    okei = fields.Char(string='Код ОКЕИ')


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def _coop_archive_upd_xml(self):
        """Сохранить XML выданных УПД вложениями под прежним `ИдФайл`.

        Выданный — проведённый исходящий счёт, по которому старый модуль
        собирает УПД. Без реквизитов (ID ЭДО, ОКПО, ИНН, руководитель…)
        он отказывает — такой УПД не выдавался, архивировать нечего.
        Повторный запуск ничего не портит: счёт с архивом пропускается.
        Ошибка на одном счёте не останавливает остальные — она в журнале.
        """
        Attachment = self.env['ir.attachment'].sudo()
        Report = self.env['ir.actions.report'].sudo()
        moves = self.sudo().search([('state', '=', 'posted'),
                                    ('move_type', '=', 'out_invoice')])
        done = set(Attachment.search([
            ('res_model', '=', 'account.move'), ('res_id', 'in', moves.ids),
            ('description', '=', ARCHIVE_NOTE)]).mapped('res_id'))
        made, unissued, failed = {}, 0, 0
        for move in moves.filtered(lambda m: m.id not in done):
            try:
                with self.env.cr.savepoint():
                    xml = Report.with_company(move.company_id)._render_qweb_xml(
                        UPD_REPORT, move.ids)[0]
                    Attachment.create({
                        'name': '%s.xml' % move.edi,
                        'res_model': 'account.move',
                        'res_id': move.id,
                        'raw': xml,
                        'mimetype': 'application/xml',
                        'description': ARCHIVE_NOTE,
                    })
                made[move.company_id.name] = made.get(move.company_id.name, 0) + 1
            except UserError:
                unissued += 1
            except Exception:
                failed += 1
                _logger.exception('Архив УПД: счёт %s не сохранён', move.display_name)
        _logger.info('Архив УПД: сохранено %s (по компаниям: %s), уже было %s, '
                     'не выдавались (нет реквизитов) %s, ошибок %s',
                     sum(made.values()), made, len(done), unissued, failed)
        return sum(made.values())
