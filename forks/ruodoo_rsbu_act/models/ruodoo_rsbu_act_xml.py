# -*- coding: utf-8 -*-
"""Электронный акт сверки в XML — формат обмена ФНС.

Приказ ФНС России от 13.05.2022 № ЕД-7-26/405@, КНД 1110332, версия 5.01,
схема ON_AKTSVEROTP (файл отправителя). Кодировка windows-1251,
кириллические имена элементов (латинских namespace нет — используется lxml,
как для прочих форм ФНС). Структура:

    Файл(ИдФайл, ВерсФорм=5.01, ВерсПрог)
      └ Документ(КНД, ДатаИнфОтпр, ВрИнфОтпр, ДатаНачПер, ДатаОкПер, НомерАкт)
          ├ СвДокКрАкт(КодОКВ) → СвОтпр / СвПол (УчастникТип)
          ├ ТаблАкт(сальдо нач/оборот/кон Деб/Кр)
          │   └ ДогСв(договор + сальдо) → ДокСв(документ) → СвОпер(операция)
          └ Подписант(ФИО, Должн)
"""
import os
import uuid
from datetime import date, datetime

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.modules import get_module_path

KND_ACT = '1110332'
ACT_FORMAT_VERSION = '5.01'


class RuodooRsbuActXml(models.Model):
    _inherit = 'ruodoo.rsbu.act'

    # ------------------------------------------------------------------
    @staticmethod
    def _d(value):
        """Дата в формате ДД.ММ.ГГГГ (как требует XSD, ДатаТип)."""
        return value.strftime('%d.%m.%Y') if value else ''

    @staticmethod
    def _amt(value):
        """Сумма: decimal с 2 знаками (totalDigits 15, fractionDigits 2)."""
        return '%.2f' % round(value or 0.0, 2)

    def _act_filename(self):
        self.ensure_one()
        company = self.company_id
        operator = (company.rsbu_edo_operator_code or '000').strip()
        sender = (company.rsbu_edo_participant_id or '').strip() \
            or str(uuid.uuid4())
        receiver = (self.partner_id.rsbu_edo_participant_id or '').strip() \
            or str(uuid.uuid4())
        today = date.today().strftime('%Y%m%d')
        guid = str(uuid.uuid4())
        return 'ON_AKTSVEROTP_%s%s_%s%s_%s_%s' % (
            operator, receiver, operator, sender, today, guid)

    def _party_node(self, etree, tag, partner, company_name=None):
        """Узел участника (СвОтпр/СвПол) по res.partner.

        ЮЛ (ИНН 10) → СвЮЛУч (НаимОрг, ИННЮЛ, КПП, ОГРН — все обязательны);
        ИП (ИНН 12) → СвИП (ФИО, ИННФЛ, ОГРНИП); иначе → СвФЛ.
        """
        attrs = {}
        if getattr(partner, 'okpo', False):
            attrs['ОКПО'] = partner.okpo
        node = etree.Element(tag, attrs)
        idsv = etree.SubElement(node, 'ИдСв')
        inn = partner._rsbu_inn()
        name = company_name or partner.name or ''
        if len(inn) == 12:
            svip = etree.SubElement(idsv, 'СвИП', {
                'ИННФЛ': inn,
                'ОГРНИП': (getattr(partner, 'ogrnip', '') or
                           getattr(partner, 'ogrn', '') or '').strip(),
            })
            self._fio_node(etree, svip, partner.name or name)
        elif len(inn) == 10:
            etree.SubElement(idsv, 'СвЮЛУч', {
                'НаимОрг': name,
                'ИННЮЛ': inn,
                'КПП': partner._rsbu_kpp(),
                'ОГРН': (getattr(partner, 'ogrn', '') or '').strip(),
            })
        else:
            svfl = etree.SubElement(idsv, 'СвФЛ', {'ИННФЛ': inn})
            self._fio_node(etree, svfl, partner.name or name)
        # Контакт — обязательный элемент (атрибуты опциональны).
        contact = {}
        if getattr(partner, 'phone', False):
            contact['Тлф'] = partner.phone
        if getattr(partner, 'email', False):
            contact['ЭлПочта'] = partner.email
        etree.SubElement(node, 'Контакт', contact)
        return node

    @staticmethod
    def _fio_node(etree, parent, full_name):
        parts = (full_name or '').split()
        attrs = {
            'Фамилия': parts[0] if parts else (full_name or '-'),
            'Имя': parts[1] if len(parts) > 1 else '-',
        }
        if len(parts) > 2:
            attrs['Отчество'] = ' '.join(parts[2:])
        return etree.SubElement(parent, 'ФИО', attrs)

    # ------------------------------------------------------------------
    def _act_build_xml(self, filename=None):
        """Собрать XML акта сверки (ON_AKTSVEROTP). Возвращает bytes."""
        self.ensure_one()
        try:
            from lxml import etree
        except ImportError:
            raise UserError(_('Для выгрузки акта требуется библиотека lxml.')) \
                from None
        self._check_requisites()
        if not self.line_ids:
            raise UserError(_(
                'Электронный акт сверки требует хотя бы одной операции за '
                'период. Нажмите «Рассчитать».'))
        if filename is None:
            filename = self._act_filename()

        company = self.company_id
        seller = company.partner_id
        buyer = self.partner_id
        now = datetime.now()

        E = etree.Element
        root = E('Файл', {
            'ИдФайл': filename,
            'ВерсФорм': ACT_FORMAT_VERSION,
            'ВерсПрог': 'RuOdoo',
        })
        doc = E('Документ', {
            'КНД': KND_ACT,
            'ДатаИнфОтпр': self._d(date.today()),
            'ВрИнфОтпр': now.strftime('%H:%M:%S'),
            'ДатаНачПер': self._d(self.date_from),
            'ДатаОкПер': self._d(self.date_to),
            'НомерАкт': self.name or '/',
        })
        root.append(doc)

        # Стороны.
        svdok = E('СвДокКрАкт', {'КодОКВ': '643'})
        svdok.append(self._party_node(etree, 'СвОтпр', seller,
                                      company_name=company.name))
        svdok.append(self._party_node(etree, 'СвПол', buyer))
        doc.append(svdok)

        # Таблица акта: один договорный блок (все операции периода),
        # сальдо/обороты на уровне ТаблАкт и ДогСв совпадают.
        totals = {
            'СальдоНачДеб': self._amt(self.opening_debit),
            'СальдоНачКр': self._amt(self.opening_credit),
            'ОборотДеб': self._amt(self.turnover_debit),
            'ОборотКр': self._amt(self.turnover_credit),
            'СальдоКонДеб': self._amt(self.closing_debit),
            'СальдоКонКр': self._amt(self.closing_credit),
        }
        tabl = E('ТаблАкт', totals)
        doc.append(tabl)

        dogsv_attrs = dict(totals)
        # Договор — из первой операции с договором либо «Основной договор».
        contract = self.line_ids.mapped('contract_id')[:1]
        dogsv_attrs['ОписТипДог'] = 'Договор'
        if contract:
            dogsv_attrs['НомДог'] = contract.display_name[:50]
        dogsv = etree.SubElement(tabl, 'ДогСв', dogsv_attrs)

        # Документы и операции. Группируем операции по документу (проводке).
        by_doc = {}
        order = []
        for line in self.line_ids:
            key = line.move_id.id or 0
            if key not in by_doc:
                by_doc[key] = []
                order.append(key)
            by_doc[key].append(line)
        for key in order:
            group = by_doc[key]
            first = group[0]
            doksv = etree.SubElement(dogsv, 'ДокСв', {
                'НаимДок': (first.doc_name or 'Операция')[:100],
                'НомДок': (first.doc_number or '-')[:50],
                'ДатаДок': self._d(first.doc_date or first.date),
            })
            for idx, line in enumerate(group, start=1):
                oper = {
                    'НомСтр': str(idx),
                    'ДатаОпер': self._d(line.date),
                    'НаимОпер': (line.name or first.doc_name
                                 or 'Операция')[:500],
                }
                if line.debit:
                    oper['СумДебет'] = self._amt(line.debit)
                if line.credit:
                    oper['СумКредит'] = self._amt(line.credit)
                etree.SubElement(doksv, 'СвОпер', oper)

        # Подписант.
        signer = company.rsbu_signatory_id or getattr(
            company, 'chief_id', False)
        podp = E('Подписант', {'СтатПодп': '1'})
        if signer and signer.partner_id.function:
            podp.set('Должн', signer.partner_id.function)
        elif getattr(company, 'rsbu_signatory_title', False):
            podp.set('Должн', company.rsbu_signatory_title)
        self._fio_node(etree, podp,
                       signer.partner_id.name if signer else (seller.name or ''))
        doc.append(podp)

        return etree.tostring(
            root, xml_declaration=True, encoding='windows-1251',
            pretty_print=True)

    # ------------------------------------------------------------------
    @api.model
    def _act_xsd_path(self):
        return os.path.join(
            get_module_path('ruodoo_rsbu_act'), 'data', 'schemas',
            'ON_AKTSVEROTP_1_972_01_05_01_01.xsd')

    def _act_validate_xml(self, xml_bytes):
        """Проверить XML по XSD. Возвращает (ok, [ошибки])."""
        from lxml import etree
        schema = etree.XMLSchema(etree.parse(self._act_xsd_path()))
        doc = etree.fromstring(xml_bytes)
        ok = schema.validate(doc)
        errors = [e.message for e in schema.error_log] if not ok else []
        return ok, errors

    def action_export_xml(self):
        """Сформировать акт сверки в XML, провалидировать, вернуть вложением."""
        self.ensure_one()
        if self.state == 'draft':
            self.action_compute()
        filename = self._act_filename()
        xml_bytes = self._act_build_xml(filename=filename)
        ok, errors = self._act_validate_xml(xml_bytes)
        if not ok:
            raise UserError(_(
                'Сформированный акт сверки не прошёл проверку по схеме '
                'ФНС:\n%s') % '\n'.join(errors[:10]))
        attachment = self.env['ir.attachment'].create({
            'name': filename + '.xml',
            'res_model': self._name,
            'res_id': self.id,
            'type': 'binary',
            'raw': xml_bytes,
            'mimetype': 'application/xml',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
