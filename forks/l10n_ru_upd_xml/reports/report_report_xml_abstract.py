# License AGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).

from xml.dom import minidom
from odoo.exceptions import UserError
from odoo.tools.translate import _
from lxml import etree

from odoo import api, models


class ReportXmlAbstract(models.AbstractModel):
    _name = "report.upd_xml.abstract"
    _description = "Abstract XML Report"

    @api.model
    def generate_report(self, ir_report, docids, data=None):
        data = data or {}
        data.setdefault("report_type", "text")

        records = self.env[ir_report.model].browse(docids)

        for s in records:
            mes = ""
            company = s.company_id or self.env.company

            # --- базовые проверки ---
            if s.name == '/':
                mes += "Отсутствует наименование документа. Проведите документ.\n"

            if not s.only_service:
                get_delivery = getattr(s, "get_delivery_doc_name", lambda: '0')
                if get_delivery() == '0':
                    mes += "Отсутствуют связанные отгрузки.\n"

            # --- компания ---
            if not company:
                mes += "Не указана компания.\n"
            else:
                if not company.edi:
                    mes += "Не указан идентификатор компании для Diadoc.\n"
                if not company.name:
                    mes += "Не указано наименование компании.\n"
                if not company.okpo:
                    mes += "Не указано ОКПО компании.\n"

                if not company.inn:
                    mes += "Не указан ИНН компании.\n"
                else:
                    if len(company.inn) == 12:
                        if not company.partner_id.last_name_IP:
                            mes += "Не указана фамилия ИП компании.\n"
                        if not company.partner_id.first_name_IP:
                            mes += "Не указано имя ИП компании.\n"
                        if not company.partner_id.middle_name_IP:
                            mes += "Не указано отчество ИП компании.\n"
                    elif len(company.inn) == 10:
                        if not company.kpp:
                            mes += "Не указан КПП компании.\n"
                    else:
                        mes += "Некорректный ИНН компании.\n"

                if not company.city:
                    mes += "Не указан город компании.\n"
                if not company.street:
                    mes += "Не указан адрес компании.\n"

                if not company.chief_id:
                    mes += "Не указан руководитель компании.\n"
                else:
                    if not company.chief_id.function:
                        mes += "Не указана должность руководителя.\n"
                    if not company.chief_id.last_name:
                        mes += "Не указана фамилия руководителя.\n"
                    if not company.chief_id.first_name:
                        mes += "Не указано имя руководителя.\n"
                    if not company.chief_id.second_name:
                        mes += "Не указано отчество руководителя.\n"

            # --- контрагент ---
            pid = s.partner_id.parent_id or s.partner_id

            if not pid:
                mes += "Не указан контрагент.\n"
            else:
                if not pid.edi:
                    mes += "Не указан идентификатор контрагента.\n"
                if not pid.name:
                    mes += "Не указано наименование контрагента.\n"
                if not pid.okpo:
                    mes += "Не указано ОКПО контрагента.\n"

                if not pid.inn:
                    mes += "Не указан ИНН контрагента.\n"
                else:
                    if len(pid.inn) == 12:
                        if not pid.last_name_IP:
                            mes += "Не указана фамилия ИП контрагента.\n"
                        if not pid.first_name_IP:
                            mes += "Не указано имя ИП контрагента.\n"
                        if not pid.middle_name_IP:
                            mes += "Не указано отчество ИП контрагента.\n"
                    elif len(pid.inn) == 10:
                        if not pid.kpp:
                            mes += "Не указан КПП контрагента.\n"
                    else:
                        mes += "Некорректный ИНН контрагента.\n"

                if not pid.city:
                    mes += "Не указан город контрагента.\n"
                if not pid.street:
                    mes += "Не указан адрес контрагента.\n"

            # --- документ ---
            if not s.edi:
                mes += "Не указан идентификатор документа.\n"
            if not s.name:
                mes += "Не указано наименование документа.\n"
            if not s.invoice_date:
                mes += "Не указана дата документа.\n"

            # --- строки ---
            if not s.invoice_line_ids:
                mes += "Отсутствуют строки.\n"
            else:
                for line in s.invoice_line_ids:
                    if not line.price_unit:
                        mes += f"Нет цены: {line.label}\n"
                    if not line.quantity:
                        mes += f"Нет количества: {line.label}\n"
                    if not line.product_uom_id.okei:
                        mes += f"Нет ОКЕИ: {line.product_uom_id.name}\n"

            # --- договор ---
            # if not s.mt_contract_id:
            #     mes += "Не указан договор.\n"
            # else:
            #     if not s.mt_contract_id.name:
            #         mes += "Нет названия договора.\n"
            #     if not s.mt_contract_id.date_start:
            #         mes += "Нет даты договора.\n"

            # --- ответственный ---
            if not s.kladov:
                mes += "Не указано ответственное лицо.\n"
            else:
                if not s.kladov.partner_id.function:
                    mes += "Не указана должность ответственного.\n"

            # ❗ если есть ошибки → стоп
            if mes:
                raise UserError(_(
                    "Не удалось сформировать УПД. Выявлены следующие ошибки:\n%s"
                ) % mes)

        data = ir_report._get_rendering_context(ir_report, docids, data)

        result_bin = ir_report._render_template(ir_report.report_name, data)

        parsed_result_bin = minidom.parseString(result_bin)
        result = parsed_result_bin.toprettyxml(indent="    ")

        result = "\n".join(
            line for line in result.splitlines() if line and not line.isspace()
        ).encode("utf8")

        content = etree.tostring(
            etree.fromstring(result),
            encoding=ir_report.xml_encoding or "WINDOWS-1251",
            xml_declaration=True,
            pretty_print=True,
        )

        return content, "xml"

    @api.model
    def _get_report_values(self, docids, data=None):
        return data or {}
