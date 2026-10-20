"""Генерация УПД (универсального передаточного документа) в XML.

Формат ФНС ON_NSCHFDOPPR (файл продавца, КНД 1115131, версия 5.03).
Источник — документ РСБУ-слоя «Счёт-фактура» (rsbu.invoice, отгрузочный).

Разделение источников (Вариант B):
  * счёт-фактурная часть (номер/дата СФ, суммы, ставка и сумма НДС, итоги)
    — из РСБУ-слоя (rsbu.invoice);
  * товарные позиции (наименование, количество, ОКЕИ, цена, ГТИН/код) —
    из связанного инвойса-источника (account.move, _source_invoice);
  * реквизиты сторон (ИНН/КПП/ОКПО/адрес), подписант — из res.company /
    res.partner (переиспользуются штатные поля l10n_ru).

Заменяет устаревший l10n_ru_upd_xml (формат 5.01 из account.move).
Кодировка windows-1251, кириллические имена элементов, валидация по XSD.
"""
import base64
from datetime import date, datetime

from odoo import _, api, models
from odoo.exceptions import UserError

KND_UPD = '1115131'
UPD_FORMAT_VERSION = '5.03'
# Отображение ставки НДС rsbu.invoice.vat_rate → значение НалСт (enum XSD).
VAT_RATE_LABEL = {
    'vat_exempt': 'без НДС',
    'vat_5': '5%',
    'vat_7': '7%',
    'vat_10': '10%',
    'vat_20': '20%',
}
# Доля ставки НДС для расчёта суммы налога (НДС = база × доля).
VAT_RATE_PCT = {
    'vat_exempt': 0.0,
    'vat_5': 0.05,
    'vat_7': 0.07,
    'vat_10': 0.10,
    'vat_20': 0.20,
}


class RsbuRealizationUpd(models.Model):
    _inherit = 'rsbu.realization'

    # ------------------------------------------------------------------
    # Реквизиты СФ (из подчинённого СФ при наличии, иначе из реализации)
    # ------------------------------------------------------------------
    def _upd_schf_number(self):
        """Номер для СвСчФакт: из отгрузочного СФ, иначе из реализации."""
        self.ensure_one()
        return (self.invoice_id.name if self.invoice_id else self.name) or ''

    def _upd_schf_date(self):
        """Дата для СвСчФакт: из отгрузочного СФ, иначе из реализации."""
        self.ensure_one()
        if self.invoice_id and self.invoice_id.date:
            return self.invoice_id.date
        return self.date or date.today()

    def _upd_vat_rate_label(self):
        """Метка ставки НДС (НалСт) — из СФ при наличии, иначе «без НДС»."""
        self.ensure_one()
        rate = self.invoice_id.vat_rate if self.invoice_id else 'vat_exempt'
        return VAT_RATE_LABEL.get(rate, 'без НДС')

    # ------------------------------------------------------------------
    # Реквизиты и вспомогательные значения
    # ------------------------------------------------------------------
    def _upd_filename(self):
        """Имя файла обмена УПД по Порядку (п.4):

            ON_NSCHFDOPPR_A_О_GGGGMMDD_N1_N2_N3_N4_N5_N6_N7

        где A — получатель «УИОЭДО+УИПол», О — отправитель «УИОЭДО+УИОтпр»;
        УИОЭДО — код оператора ЭДО (3 симв, «000» без оператора); УИПол/
        УИОтпр — идентификаторы участников в ЭДО (или GUID вне ЭДО); N1 —
        36-символьный GUID (совпадает с ИдФайл); N2–N6 — флаги прослежива-
        емости/маркировки (0); N7 — двузначный код (00).
        """
        self.ensure_one()
        import uuid
        company = self.company_id
        operator = (company.rsbu_edo_operator_code or '000').strip()
        # Отправитель (продавец) — идентификатор нашей организации в ЭДО.
        sender = (company.rsbu_edo_participant_id or '').strip() \
            or str(uuid.uuid4())
        # Получатель (покупатель) — идентификатор контрагента в ЭДО.
        receiver = (self.partner_id.rsbu_edo_participant_id or '').strip() \
            or str(uuid.uuid4())
        a = '%s%s' % (operator, receiver)   # А — получатель
        o = '%s%s' % (operator, sender)     # О — отправитель
        today = date.today().strftime('%Y%m%d')
        guid = str(uuid.uuid4())            # N1
        # N2..N7 — признаки прослеживаемости/маркировки/спецрежимов (по
        # умолчанию отсутствуют).
        flags = '0_0_0_0_0_00'
        return 'ON_NSCHFDOPPR_%s_%s_%s_%s_%s' % (a, o, today, guid, flags)

    def _upd_validate(self):
        """Проверить наличие данных, обязательных для УПД."""
        self.ensure_one()
        errors = []
        company = self.company_id
        partner = company.partner_id
        if not partner.inn:
            errors.append(_('ИНН организации-продавца'))
        if not self.partner_id:
            errors.append(_('контрагент-покупатель'))
        elif not self.partner_id.inn:
            errors.append(_('ИНН покупателя'))
        source = self._source_invoice()
        if not source:
            errors.append(_('инвойс-источник с товарными позициями'))
        elif not source.invoice_line_ids:
            errors.append(_('строки инвойса-источника'))
        else:
            for line in source.invoice_line_ids.filtered(
                    lambda l: l.display_type in (False, 'product')):
                uom = line.product_uom_id
                if uom and not getattr(uom, 'okei', False):
                    errors.append(
                        _('код ОКЕИ для единицы «%s»') % uom.name)
                    break
        if not company.rsbu_signatory_id and not getattr(
                company, 'chief_id', False):
            errors.append(_('подписант (руководитель) организации'))
        if errors:
            raise UserError(_(
                'Не удалось сформировать УПД. Не хватает данных:\n%s')
                % '\n'.join('— %s' % e for e in errors))

    @staticmethod
    def _amt(value):
        """Денежная сумма УПД: строка с 2 знаками (СтТовБезНДС/СтТовУчНал)."""
        return '%.2f' % (value or 0.0)

    @staticmethod
    def _qty(value):
        """Количество/цена: до 11 знаков дробной части, без хвостовых нулей."""
        s = ('%.11f' % (value or 0.0)).rstrip('0').rstrip('.')
        return s or '0'

    def _upd_party_node(self, etree, tag, partner, okpo=True):
        """Узел стороны (СвПрод/СвПокуп/ГрузОтпр/ГрузПолуч) по res.partner.

        ЮЛ (ИНН 10) → СвЮЛУч; ИП (ИНН 12) → СвИП. Адрес — упрощённый АдрИнф
        (код страны 643, текстом). Реквизиты штатные (l10n_ru).
        """
        attrs = {}
        if okpo and getattr(partner, 'okpo', False):
            attrs['ОКПО'] = partner.okpo
        node = etree.Element(tag, attrs)
        idsv = etree.SubElement(node, 'ИдСв')
        inn = (partner.inn or '').strip()
        if len(inn) == 12:
            names = (partner.name or '').replace('ИП', '').split()
            svip = etree.SubElement(idsv, 'СвИП', {
                'ИННФЛ': inn, 'ИныеСвед': partner.name or ''})
            etree.SubElement(svip, 'ФИО', {
                'Фамилия': names[0] if names else partner.name or '',
                'Имя': names[1] if len(names) > 1 else '-',
                **({'Отчество': names[2]} if len(names) > 2 else {}),
            })
        else:
            etree.SubElement(idsv, 'СвЮЛУч', {
                'НаимОрг': partner.name or '',
                'ИННЮЛ': inn,
                **({'КПП': partner.kpp} if getattr(partner, 'kpp', False)
                   else {}),
            })
        # Адрес текстом (АдрИнф) — упрощённый, достаточно по XSD.
        addr = etree.SubElement(node, 'Адрес')
        parts = [partner.city or '', partner.street or '']
        etree.SubElement(addr, 'АдрИнф', {
            'КодСтр': '643',
            'НаимСтран': 'Российская Федерация',
            'АдрТекст': ', '.join(p for p in parts if p) or 'н/д',
        })
        return node

    # ------------------------------------------------------------------
    # Сборка XML УПД
    # ------------------------------------------------------------------
    def _upd_build_xml(self, filename=None):
        """Собрать XML УПД (формат 5.03) через lxml. Возвращает bytes."""
        self.ensure_one()
        try:
            from lxml import etree
        except ImportError:
            raise UserError(_('Для выгрузки УПД требуется библиотека lxml.')) from None
        self._upd_validate()
        if filename is None:
            filename = self._upd_filename()

        company = self.company_id
        seller = company.partner_id
        buyer = self.partner_id
        source = self._source_invoice()
        now = datetime.now()

        E = etree.Element
        root = E('Файл', {
            'ИдФайл': filename,
            'ВерсФорм': UPD_FORMAT_VERSION,
            'ВерсПрог': 'RuOdoo',
        })
        has_sf = bool(self.invoice_id)
        if has_sf:
            naim_dok_opr = ('Счет-фактура и документ об отгрузке товаров '
                            '(выполнении работ), передаче имущественных прав '
                            '(документ об оказании услуг)')
        else:
            naim_dok_opr = ('Документ об отгрузке товаров (выполнении работ), '
                            'передаче имущественных прав (документ об '
                            'оказании услуг)')
        doc = E('Документ', {
            'КНД': KND_UPD,
            'Функция': 'СЧФДОП' if has_sf else 'ДОП',
            'ПоФактХЖ': 'Документ об отгрузке товаров (выполнении работ), '
                        'передаче имущественных прав (документ об оказании '
                        'услуг)',
            'НаимДокОпр': naim_dok_opr,
            'ДатаИнфПр': now.strftime('%d.%m.%Y'),
            'ВремИнфПр': now.strftime('%H.%M.%S'),
            'НаимЭконСубСост': company.name or '',
        })
        root.append(doc)

        # СвСчФакт: номер и дата — из подчинённого СФ при наличии, иначе из
        # документа реализации (ветка «2»/ДОП, 03 §6.3). XSD требует СвСчФакт
        # с НомерДок/ДатаДок независимо от Функции.
        schf = E('СвСчФакт', {
            'НомерДок': self._upd_schf_number(),
            'ДатаДок': self._upd_schf_date().strftime('%d.%m.%Y'),
        })
        doc.append(schf)
        # Продавец / покупатель.
        schf.append(self._upd_party_node(etree, 'СвПрод', seller))
        # Грузоотправитель (если задан и отличается от продавца) / «он же».
        shipper = self.upd_shipper_id
        gruzot = E('ГрузОт')
        if shipper and shipper != seller:
            gruzot.append(self._upd_party_node(etree, 'ГрузОтпр', shipper))
        else:
            etree.SubElement(gruzot, 'ОнЖе').text = 'он же'
        doc_has_shipment = any(
            (l.product_id.type != 'service')
            for l in source.invoice_line_ids) if source else False
        if doc_has_shipment:
            schf.append(gruzot)
            consignee = self.upd_consignee_id or buyer
            schf.append(self._upd_party_node(
                etree, 'ГрузПолуч', consignee))
        schf.append(self._upd_party_node(etree, 'СвПокуп', buyer))
        # Денежный измеритель — рубли.
        etree.SubElement(schf, 'ДенИзм', {
            'КодОКВ': '643', 'НаимОКВ': 'Российский рубль'})

        # ТаблСчФакт: позиции из инвойса-источника, финансы из РСБУ/строки.
        tabl = E('ТаблСчФакт')
        doc.append(tabl)
        sf_vat_rate = self.invoice_id.vat_rate if self.invoice_id \
            else 'vat_exempt'
        rate_label = VAT_RATE_LABEL.get(sf_vat_rate, 'без НДС')
        # Метка ставки — из РСБУ (vat_rate). Суммы НДС берутся ФАКТИЧЕСКИЕ
        # из строки инвойса-источника (price_total − price_subtotal): это
        # корректно и для ставки «в том числе» (расчётная 5/105), где налог
        # выделяется из цены, а не начисляется сверху. Fallback (нет налогов
        # в источнике) — пересчёт по ставке РСБУ.
        vat_pct = VAT_RATE_PCT.get(sf_vat_rate, 0.0)
        total_wo_vat = 0.0
        total_vat = 0.0
        total_with_vat = 0.0
        lines = source.invoice_line_ids.filtered(
            lambda l: l.display_type in (False, 'product')) if source \
            else self.env['account.move.line']
        for idx, line in enumerate(lines, start=1):
            # База (без НДС) — стоимость позиции из инвойса-источника.
            subtotal = line.price_subtotal
            if line.tax_ids:
                line_vat = round((line.price_total or 0.0) - subtotal, 2)
                total = round(line.price_total or 0.0, 2)
            else:
                line_vat = round(subtotal * vat_pct, 2)
                total = round(subtotal + line_vat, 2)
            total_wo_vat += subtotal
            total_vat += line_vat
            total_with_vat += total
            uom = line.product_uom_id
            sved = E('СведТов', {
                'НомСтр': str(idx),
                'НаимТов': line.name or (line.product_id.name or 'Товар'),
                'НаимЕдИзм': uom.name or '',
                'КолТов': self._qty(line.quantity),
                'ЦенаТов': self._qty(
                    subtotal / line.quantity if line.quantity else 0.0),
                'СтТовБезНДС': self._amt(subtotal),
                'НалСт': rate_label,
                'СтТовУчНал': self._amt(total),
            })
            if uom and getattr(uom, 'okei', False):
                sved.set('ОКЕИ_Тов', uom.okei)
            # Доп. сведения товара (код/ГТИН) — из product.
            product = line.product_id
            dop_attrs = {}
            if product.default_code:
                dop_attrs['КодТов'] = product.default_code
            if product.barcode:
                dop_attrs['ГТИН'] = ('0' + product.barcode)[-14:]
            if dop_attrs:
                etree.SubElement(sved, 'ДопСведТов', dop_attrs)
            # Сумма НДС по строке.
            sumnal = etree.SubElement(sved, 'СумНал')
            if line_vat:
                etree.SubElement(sumnal, 'СумНал').text = self._amt(line_vat)
            else:
                etree.SubElement(sumnal, 'БезНДС').text = 'без НДС'
            tabl.append(sved)

        vsego = E('ВсегоОпл', {
            'СтТовБезНДСВсего': self._amt(total_wo_vat),
            'СтТовУчНалВсего': self._amt(total_with_vat),
        })
        sumnal_all = etree.SubElement(vsego, 'СумНалВсего')
        if round(total_vat, 2):
            etree.SubElement(sumnal_all, 'СумНал').text = self._amt(total_vat)
        else:
            etree.SubElement(sumnal_all, 'БезНДС').text = 'без НДС'
        tabl.append(vsego)

        # СвПродПер: передача, ответственное лицо (кладовщик), транспорт.
        svprodper = E('СвПродПер')
        doc.append(svprodper)
        svper = E('СвПер', {
            'СодОпер': self.upd_operation_content or 'Товары/услуги переданы',
            'ДатаПер': (self.date or date.today()).strftime('%d.%m.%Y'),
        })
        svprodper.append(svper)
        # Основание передачи.
        etree.SubElement(svper, 'ОснПер', {
            'РеквНаимДок': 'Договор',
            'РеквНомерДок': self.upd_basis or (self.name or ''),
            'РеквДатаДок': (self.date or date.today()).strftime('%d.%m.%Y'),
        })
        transferer = self.upd_transferred_by_id
        if transferer:
            svlic = etree.SubElement(svper, 'СвЛицПер')
            names = (transferer.name or '').split()
            rab = etree.SubElement(svlic, 'РабОргПрод', {
                'Должность': (transferer.partner_id.function or 'Кладовщик'),
            })
            etree.SubElement(rab, 'ФИО', {
                'Фамилия': names[0] if names else (transferer.name or '-'),
                'Имя': names[1] if len(names) > 1 else '-',
                **({'Отчество': names[2]} if len(names) > 2 else {}),
            })
        if self.upd_transport:
            etree.SubElement(svper, 'Тран', {'СвТран': self.upd_transport})

        # Подписант (руководитель организации-продавца).
        signer = company.rsbu_signatory_id or getattr(company, 'chief_id',
                                                       False)
        podp = E('Подписант', {
            'СпосПодтПолном': '1',
            **({'Должн': signer.partner_id.function}
               if signer and signer.partner_id.function else {}),
        })
        if signer:
            names = (signer.name or '').split()
            etree.SubElement(podp, 'ФИО', {
                'Фамилия': names[0] if names else (signer.name or '-'),
                'Имя': names[1] if len(names) > 1 else '-',
                **({'Отчество': names[2]} if len(names) > 2 else {}),
            })
        doc.append(podp)

        return etree.tostring(
            root, xml_declaration=True, encoding='windows-1251',
            pretty_print=True)

    # ------------------------------------------------------------------
    # Валидация против XSD и выгрузка
    # ------------------------------------------------------------------
    @api.model
    def _upd_xsd_path(self):
        import os
        from odoo.modules import get_module_path
        return os.path.join(
            get_module_path('rsbu_fns_reporting'), 'data', 'schemas',
            'ON_NSCHFDOPPR_1_997_01_05_03_02.xsd')

    def _upd_validate_xml(self, xml_bytes):
        """Валидация УПД против XSD. Возвращает (ok, errors)."""
        from lxml import etree
        schema = etree.XMLSchema(etree.parse(self._upd_xsd_path()))
        doc = etree.fromstring(xml_bytes)
        ok = schema.validate(doc)
        errors = [e.message for e in schema.error_log] if not ok else []
        return ok, errors

    def action_export_upd_xml(self):
        """Сформировать УПД в XML, провалидировать и вернуть вложением."""
        self.ensure_one()
        filename = self._upd_filename()
        xml_bytes = self._upd_build_xml(filename=filename)
        ok, errors = self._upd_validate_xml(xml_bytes)
        if not ok:
            raise UserError(_(
                'Сформированный УПД не прошёл проверку по схеме ФНС:\n%s')
                % '\n'.join(errors[:10]))
        attachment = self.env['ir.attachment'].create({
            'name': filename + '.xml',
            'res_model': self._name,
            'res_id': self.id,
            'type': 'binary',
            'datas': base64.b64encode(xml_bytes),
            'mimetype': 'application/xml',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
