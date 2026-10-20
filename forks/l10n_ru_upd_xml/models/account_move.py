from odoo import api, fields, models, _
import hashlib
import re
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    edi = fields.Char(string='ID EDI', compute='_compute_sh1_edi')
    kpp = fields.Char(string='КПП', compute='_compute_get_kpp')

    def _compute_get_kpp(self):
        for s in self:
            pid = self.partner_id.parent_id or self.partner_id

            s.kpp = pid.kpp if (s.partner_id == s.partner_shipping_id or not s.partner_shipping_id) else s.partner_shipping_id.kpp

    @api.depends('name')
    def _compute_sh1_edi(self):
        # В Odoo 20 у черновика name == False (раньше '/'), а compute вызывается
        # и на наборе записей, поэтому считаем по одной и берём имя или пустую строку.
        for s in self:
            hash_object = hashlib.sha1((s.name or '').encode('utf-8'), usedforsecurity=False)
            pid = s.partner_id.parent_id or s.partner_id
            operator = s.company_id.edi_operator or '2BM'
            s.edi = 'ON_NSCHFDOPPR_%s_%s_%s' % (
                self._edi_participant(pid.edi, operator),
                self._edi_participant(s.company_id.edi, operator),
                hash_object.hexdigest())

    @staticmethod
    def _edi_participant(value, operator):
        """ID участника ЭДО с кодом оператора впереди.

        Полный ID (`2AL-…`) оставляем как есть; голый — дополняем кодом
        оператора из настроек компании. Прежде код `2BM-` был вшит и ставился
        только получателю, а у отправителя его не было вовсе.
        """
        value = (value or '').strip()
        if not value or re.match(r'^[0-9A-Z]{3}-', value):
            return value
        return '%s-%s' % (operator, value)

    def print_upd(self):
        for s in self:
            mes = str(s.check_correct_upd()).strip()
            if mes != "":
                raise UserError(_(f"Не удалось сформировать УПД. Выявлены следующие ошибки:\n{mes}"))
            else:
                return self.env.ref('l10n_ru_upd_xml.upd_xml_report').sudo().report_action(s.id)  # render_qweb_xml(s.id)

    def check_correct_upd(self, manually=True):
        for s in self:
            mes = ""
            company = s.company_id
            if s.name == '/':
                mes += "Отсутствует наименование документа. Проверидите документ, чтобы назваие сформировалось автоматически.\n"
            if not s.only_service and s.get_delivery_doc_name() == '0':
                mes += "Отсутствуют связанные отгрузки.\n"
            if not company:
                company = self.env.company
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
                            mes += "Не указана фамилия ИП для вашей компании.\n"
                        if not company.partner_id.first_name_IP:
                            mes += "Не указано имя ИП для вашей компании.\n"
                        if not company.partner_id.middle_name_IP:
                            mes += "Не указано отчество ИП для вашей компании.\n"
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
                        mes += "Не указана должность руководителя компании.\n"
                    if not company.chief_id.last_name:
                        mes += "Не указана фамилия руководителя компании.\n"
                    if not company.chief_id.first_name:
                        mes += "Не указано имя руководителя компании.\n"
                    if not company.chief_id.second_name:
                        mes += "Не указано отчество руководителя компании.\n"
            pid = s.partner_id.parent_id
            if not pid:
                pid = s.partner_id
            if not pid:
                mes += "Не указан контрагент.\n"
            else:
                if not pid.edi:
                    mes += "Не указан идентификатор контрагента для Diadoc.\n"
                if not pid.name:
                    mes += "Не указано наименование контрагента.\n"
                if not pid.okpo:
                    mes += "Не указано ОКПО контрагента.\n"
                if not pid.inn:
                    mes += "Не указан ИНН контрагента.\n"
                else:
                    if len(pid.inn) == 12:
                        if not pid.last_name_IP:
                            mes += "Не указана фамилия ИП для контрагента.\n"
                        if not pid.first_name_IP:
                            mes += "Не указано имя ИП для контрагента.\n"
                        if not pid.middle_name_IP:
                            mes += "Не указано отчество ИП для контрагента.\n"
                    elif len(pid.inn) == 10:
                        if not pid.kpp:
                            mes += "Не указан КПП контрагента.\n"
                    else:
                        mes += "Некорректный ИНН контрагента.\n"
                if not pid.city:
                    mes += "Не указан город контрагента.\n"
                if not pid.street:
                    mes += "Не указан адрес контрагента.\n"
            if manually:
                if not s.edi:
                    mes += "Не указан идентификатор документа для Diadoc.\n"
                if not s.name:
                    mes += "Не указано наименование документа\n"
                if not s.invoice_date:
                    mes += "Не указана дата документа\n"
            if not s.only_service:
                gruzootpr = s.gruzootpr
                if not gruzootpr:
                    gruzootpr = pid
                if gruzootpr.parent_id:
                    gruzootpr = gruzootpr.parent_id
                if not gruzootpr:
                    mes += "Не указан грузоотправитель.\n"
                else:
                    if not gruzootpr.name:
                        mes += "Не указано наименование грузоотправителя.\n"
                    if not gruzootpr.okpo:
                        mes += "Не указано ОКПО грузоотправителя.\n"
                    if not gruzootpr.inn:
                        mes += "Не указан ИНН грузоотправителя.\n"
                    else:
                        if len(gruzootpr.inn) == 12:
                            if not gruzootpr.last_name_IP:
                                mes += "Не указана фамилия ИП для грузоотправителя.\n"
                            if not gruzootpr.first_name_IP:
                                mes += "Не указано имя ИП для грузоотправителя.\n"
                            if not gruzootpr.middle_name_IP:
                                mes += "Не указано отчество ИП для грузоотправителя.\n"
                        elif len(gruzootpr.inn) == 10:
                            if not gruzootpr.kpp:
                                mes += "Не указан КПП грузоотправителя.\n"
                        else:
                            mes += "Некорректный ИНН грузоотправителя.\n"
                    if not gruzootpr.city:
                        mes += "Не указан город грузоотправителя.\n"
                    if not gruzootpr.street:
                        mes += "Не указан адрес грузоотправителя.\n"
                gruzopol = s.gruzopol
                if not gruzopol:
                    gruzopol = pid
                if gruzopol.parent_id:
                    gruzopol = gruzopol.parent_id
                if not gruzopol:
                    mes += "Не указан грузополучатель.\n"
                else:
                    if not gruzopol.name:
                        mes += "Не указано наименование грузополучателя.\n"
                    if not gruzopol.okpo:
                        mes += "Не указано ОКПО грузополучателя.\n"
                    if not gruzopol.inn:
                        mes += "Не указан ИНН грузополучателя.\n"
                    else:
                        if len(gruzopol.inn) == 12:
                            if not gruzopol.last_name_IP:
                                mes += "Не указана фамилия ИП для грузополучателя.\n"
                            if not gruzopol.first_name_IP:
                                mes += "Не указано имя ИП для грузополучателя.\n"
                            if not gruzopol.middle_name_IP:
                                mes += "Не указано отчество ИП для грузополучателя.\n"
                        elif len(gruzopol.inn) == 10:
                            if not gruzopol.kpp:
                                mes += "Не указан КПП грузополучателя.\n"
                        else:
                            mes += "Некорректный ИНН грузополучателя.\n"
                    if not gruzopol.city:
                        mes += "Не указан город грузополучателя.\n"
                    if not gruzopol.street:
                        mes += "Не указан адрес грузополучателя.\n"
            if s.payment_num:
                if not s.payment_date:
                    mes += "Не указана дата платежки в УПД.\n"
            if not s.invoice_line_ids:
                mes += "Отсутствуют строки заказа.\n"
            else:
                for line in s.invoice_line_ids:
                    if not line.price_unit:
                        mes += u"Не указана цена за единицу для товара {}.\n".format(line.label)
                    if not line.quantity:
                        mes += u"Не указано количество для товара {}.\n".format(line.label)
                    if not line.product_uom_id.okei:
                        mes += u"Не указан код ОКЕИ для единицы измерения {}.\n".format(line.product_uom_id.name)
            # mt_contract_id заводит l10n_ru_contract (и то в неподключённом файле), от
            # него этот модуль не зависит - проверяем договор, только если поле есть.
            if 'mt_contract_id' not in s._fields:
                pass
            elif not s.mt_contract_id:
                mes += u"Не указан договор.\n"
            else:
                if not s.mt_contract_id.name:
                    mes += "Не указано наименование договора.\n"
                if not s.mt_contract_id.date_start:
                    mes += "Не указана дата договора.\n"
            if not s.kladov:
                mes += "Не указано лицо, ответственное за передачу товаров/услуг.\n"
            else:
                if not s.kladov.partner_id.function:
                    mes += "Не указана должность лица, ответственного за передачу товаров/услуг.\n"
            return str(mes)
