# -*- coding: utf-8 -*-
"""Данные для печатной формы УПД (DOCX) из документа РСБУ-слоя.

Печатный УПД (docx_report) строится из документа «Счёт-фактура» РСБУ-слоя
(rsbu.invoice, отгрузочный), как и XML-выгрузка (Вариант B):
  * счёт-фактурная часть (номер/дата, ставка, суммы/итоги) — из rsbu.invoice;
  * товарные позиции — из связанного инвойса-источника (_source_invoice);
  * стороны и подписант — из res.company / res.partner.

Логика пересчёта НДС по строке совпадает с rsbu_upd_xml (НДС = база ×
ставка РСБУ). Методы публичные, т.к. вызываются из docxtpl-шаблона как
``docs.upd_docx_*()`` (Jinja не обращается к «приватным» _методам).
"""
from odoo import models

# Переиспользуем справочники ставок из XML-генератора.
from .rsbu_upd_xml import VAT_RATE_LABEL, VAT_RATE_PCT


class RsbuRealizationUpdDocx(models.Model):
    _inherit = 'rsbu.realization'

    # ------------------------------------------------------------------
    @staticmethod
    def _upd_fio(user_or_partner):
        """ФИО и должность подписанта/ответственного лица."""
        partner = getattr(user_or_partner, 'partner_id', user_or_partner)
        name = (getattr(user_or_partner, 'name', '') or
                getattr(partner, 'name', '') or '')
        function = getattr(partner, 'function', '') or ''
        return {'name': name, 'function': function}

    def upd_vat_label(self):
        """Текстовая метка ставки НДС (напр. «5%», «без НДС»).

        Ставка берётся из подчинённого СФ при наличии, иначе «без НДС».
        """
        self.ensure_one()
        rate = self.invoice_id.vat_rate if self.invoice_id else 'vat_exempt'
        return VAT_RATE_LABEL.get(rate, 'без НДС')

    def upd_docx_status(self):
        """Статус УПД: «1» — счёт-фактура + передаточный документ;
        «2» — только передаточный документ (без НДС).

        Структурный драйвер — наличие подчинённого отгрузочного СФ
        (self.invoice_id), тот же, что в XML (Функция)."""
        self.ensure_one()
        return '1' if self.invoice_id else '2'

    @staticmethod
    def _bank_requisites(partner):
        """Банковские реквизиты стороны (Р/с, Банк, БИК, К/с) одной строкой."""
        bank = False
        if partner.bank_ids:
            bank = partner.bank_ids[0]
        elif partner.parent_id and partner.parent_id.bank_ids:
            bank = partner.parent_id.bank_ids[0]
        if not bank:
            return ''
        parts = []
        if bank.account_number:
            parts.append('Р/с %s' % bank.account_number)
        name = getattr(bank, 'bank_name', '') or (
            bank.bank_id.name if bank.bank_id else '')
        if name:
            parts.append(name)
        bic = getattr(bank, 'bank_bic', '') or (
            bank.bank_id.bic if bank.bank_id else '')
        if bic:
            parts.append('БИК %s' % bic)
        corr = getattr(bank, 'bank_corr_acc', '') or ''
        if corr:
            parts.append('к/с %s' % corr)
        return ', '.join(parts)

    def upd_docx_lines(self):
        """Товарные позиции УПД (16 колонок счёта-фактуры, Пост. № 1137).

        А(код), 1(№), 1а(наимен), 1б(код вида), 2(ОКЕИ), 2а(ед.изм.),
        3(кол-во), 4(цена), 5(без НДС), 6(акциз), 7(ставка), 8(НДС),
        9(с НДС), 10/10а(страна), 11(ДТ).

        Суммы берутся ФАКТИЧЕСКИЕ из строки инвойса-источника: база =
        price_subtotal, НДС = price_total − price_subtotal (корректно и для
        ставки «в том числе», где налог выделяется из цены, а не начисляется
        сверху), стоимость с НДС = price_total. Если у строки нет налогов,
        но в rsbu.invoice задана ставка — НДС пересчитывается по ставке
        (fallback для источников без налогов Odoo).
        """
        self.ensure_one()
        source = self._source_invoice()
        sf_vat_rate = self.invoice_id.vat_rate if self.invoice_id \
            else 'vat_exempt'
        vat_pct = VAT_RATE_PCT.get(sf_vat_rate, 0.0)
        rate_label = self.upd_vat_label()
        lines = source.invoice_line_ids.filtered(
            lambda l: l.display_type in (False, 'product')) if source \
            else self.env['account.move.line']
        rows = []
        for idx, line in enumerate(lines, start=1):
            subtotal = line.price_subtotal or 0.0
            if line.tax_ids:
                # Фактический НДС строки (учитывает «в т.ч.»/«сверху»).
                line_vat = round((line.price_total or 0.0) - subtotal, 2)
                total = round(line.price_total or 0.0, 2)
            else:
                # Нет налогов в источнике — пересчёт по ставке РСБУ.
                line_vat = round(subtotal * vat_pct, 2)
                total = round(subtotal + line_vat, 2)
            qty = line.quantity or 0.0
            uom = line.product_uom_id
            product = line.product_id
            rows.append({
                'num': idx,
                'code': product.default_code or '',          # А
                'name': line.label or (product.name or 'Товар'),  # 1а (Odoo 20: label)
                'type_code': '',                              # 1б (прослеж.)
                'okei': getattr(uom, 'okei', '') or '',       # 2
                'uom': uom.name or '',                        # 2а
                'qty': qty,                                   # 3
                'price': round(subtotal / qty, 2) if qty else 0.0,  # 4
                'subtotal': subtotal,                         # 5
                'excise': 'Без акциза',                       # 6
                'vat_label': rate_label if line_vat else 'без НДС',  # 7
                'vat': line_vat,                              # 8
                'vat_cell': ('%.2f' % line_vat) if line_vat else 'без НДС',
                'total': total,                               # 9
                'country_code': '',                           # 10
                'country': '',                                # 10а
                'customs_decl': '',                           # 11
            })
        return rows

    def upd_docx_totals(self):
        """Итоги УПД: без НДС, НДС, с НДС (по фактическим суммам строк)."""
        self.ensure_one()
        rows = self.upd_docx_lines()
        wo_vat = round(sum(r['subtotal'] for r in rows), 2)
        vat = round(sum(r['vat'] for r in rows), 2)
        with_vat = round(sum(r['total'] for r in rows), 2)
        return {'wo_vat': wo_vat, 'vat': vat, 'with_vat': with_vat}

    @staticmethod
    def _clean_address(partner):
        """Почтовый адрес без наименования организации (для строк 2а/6а).

        contact_address начинается с названия партнёра — убираем первую
        строку с именем и собираем адрес из полей.
        """
        parts = []
        if partner.zip:
            parts.append(partner.zip)
        if getattr(partner, 'state_id', False) and partner.state_id:
            parts.append(partner.state_id.name)
        if partner.city:
            parts.append(partner.city)
        if partner.street:
            parts.append(partner.street)
        if partner.street2:
            parts.append(partner.street2)
        if parts:
            return ', '.join(parts)
        # Фолбэк: contact_address без первой строки (имени).
        addr = (partner.contact_address or '').split('\n')
        tail = [a.strip() for a in addr[1:] if a.strip()]
        return ', '.join(tail)

    def _party_dict(self, partner, name=None):
        return {
            'name': name or partner.name or '',
            'inn': partner._coop_upd_inn(),
            'kpp': partner._coop_upd_kpp(),
            'okpo': getattr(partner, 'okpo', '') or '',
            'address': self._clean_address(partner),
            'bank': self._bank_requisites(partner),
        }

    def upd_docx_seller(self):
        """Реквизиты продавца (из организации) с банковскими реквизитами."""
        self.ensure_one()
        return self._party_dict(self.company_id.partner_id,
                                self.company_id.name)

    def upd_docx_buyer(self):
        """Реквизиты покупателя (из контрагента) с банковскими реквизитами."""
        self.ensure_one()
        return self._party_dict(self.partner_id)

    def upd_docx_shipper(self):
        """Грузоотправитель (3): задан явно или «он же» (= продавец)."""
        self.ensure_one()
        if self.upd_shipper_id and self.upd_shipper_id != \
                self.company_id.partner_id:
            p = self.upd_shipper_id
            return '%s, %s' % (p.name or '', self._clean_address(p))
        return 'он же'

    def upd_docx_consignee(self):
        """Грузополучатель (4): задан явно или покупатель."""
        self.ensure_one()
        p = self.upd_consignee_id or self.partner_id
        return '%s, %s' % (p.name or '', self._clean_address(p))

    def upd_docx_basis(self):
        """Основание передачи (10): договор/документ-основание."""
        self.ensure_one()
        return self.upd_basis or (self.name or '')

    def upd_docx_shipment_doc(self):
        """Документ об отгрузке (5а)."""
        self.ensure_one()
        return 'Универсальный передаточный документ № %s от %s' % (
            self.name or '', self.date.strftime('%d.%m.%Y') if self.date
            else '')

    def upd_docx_receiver(self):
        """Лицо со стороны покупателя, принявшее груз (17/20)."""
        self.ensure_one()
        if not self.upd_received_by_id:
            return {'name': '', 'function': ''}
        data = self._upd_fio(self.upd_received_by_id)
        if not data['function']:
            data['function'] = 'Директор'
        return data

    def upd_docx_seller_subject(self):
        """Наименование экономического субъекта — продавца (16)."""
        self.ensure_one()
        p = self.company_id.partner_id
        return '%s, ИНН/КПП %s/%s' % (
            self.company_id.name or '', p._coop_upd_inn(),
            p._coop_upd_kpp())

    def upd_docx_buyer_subject(self):
        """Наименование экономического субъекта — покупателя (21)."""
        self.ensure_one()
        p = self.partner_id
        kpp = p._coop_upd_kpp()
        return '%s%s' % (p.name or '',
                         ', ИНН/КПП %s/%s' % (p._coop_upd_inn(), kpp)
                         if p._coop_upd_inn() else '')

    def upd_docx_signer(self):
        """Подписант (руководитель организации-продавца)."""
        self.ensure_one()
        signer = self.company_id.rsbu_signatory_id or getattr(
            self.company_id, 'chief_id', False)
        if not signer:
            return {'name': '', 'function': 'Руководитель'}
        data = self._upd_fio(signer)
        if not data['function']:
            data['function'] = (
                self.company_id.rsbu_signatory_title
                if hasattr(self.company_id, 'rsbu_signatory_title')
                else 'Руководитель') or 'Руководитель'
        return data

    def upd_docx_transferer(self):
        """Лицо, передавшее товар (кладовщик) — для «Товар передал»."""
        self.ensure_one()
        if not self.upd_transferred_by_id:
            return {'name': '', 'function': ''}
        data = self._upd_fio(self.upd_transferred_by_id)
        if not data['function']:
            data['function'] = 'Кладовщик'
        return data

    # ------------------------------------------------------------------
    def _upd_docx_report(self, with_stamp=True):
        xmlid = ('rsbu_fns_reporting.docx_template_rsbu_upd' if with_stamp
                 else 'rsbu_fns_reporting.docx_template_rsbu_updn')
        template = self.env.ref(xmlid, raise_if_not_found=False)
        return template.report_id if template else False

    def action_print_upd_docx(self):
        """Печать УПД (DOCX, с печатями) из отгрузочного СФ."""
        self.ensure_one()
        from odoo.exceptions import UserError
        from odoo import _
        report = self._upd_docx_report(with_stamp=True)
        if not report:
            raise UserError(_('Не найден DOCX-шаблон УПД.'))
        return report.report_action(self)

    def action_print_updn_docx(self):
        """Печать УПД без печатей (DOCX) из отгрузочного СФ."""
        self.ensure_one()
        from odoo.exceptions import UserError
        from odoo import _
        report = self._upd_docx_report(with_stamp=False)
        if not report:
            raise UserError(_('Не найден DOCX-шаблон УПД.'))
        return report.report_action(self)
