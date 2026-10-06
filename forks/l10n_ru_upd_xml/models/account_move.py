from odoo import api, fields, models, _
import hashlib
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    edi = fields.Char(string=_('ID EDI'), compute='_compute_sh1_edi')
    kpp = fields.Char(string=_('КПП'), compute='_compute_get_kpp')

    def _compute_get_kpp(self):
        for s in self:
            pid = self.partner_id.parent_id or self.partner_id

            s.kpp = pid.kpp if (s.partner_id == s.partner_shipping_id or not s.partner_shipping_id) else s.partner_shipping_id.kpp

    @api.depends('name')
    def _compute_sh1_edi(self):
        hash_object = hashlib.sha1((self.name).encode('utf-8'))
        pid = self.partner_id.parent_id or self.partner_id
        self.edi = 'ON_NSCHFDOPPR_2BM-' + str(pid.edi) + '_' + str(self.company_id.edi) + '_' + hash_object.hexdigest()

    def print_upd(self):
        for s in self:
            mes = str(s.check_correct_upd()).strip()
            if mes != "":
                raise UserError(_(u"Не удалось сформировать УПД. Выявлены следующие ошибки:\n{}".format(mes)))
            else:
                return self.env.ref('l10n_ru_upd_xml.upd_xml_report').sudo().report_action(s.id)  # render_qweb_xml(s.id)

    def check_correct_upd(self, manually=True):
        for s in self:
            mes = ""
            company = s.company_id
            if s.name == '/':
                mes += u"Отсутствует наименование документа. Проверидите документ, чтобы назваие сформировалось автоматически.\n"
            if not s.only_service and s.get_delivery_doc_name() == '0':
                mes += u"Отсутствуют связанные отгрузки.\n"
            if not company:
                company = self.env.company
            if not company:
                mes += u"Не указана компания.\n"
            else:
                if not company.edi:
                    mes += u"Не указан идентификатор компании для Diadoc.\n"
                if not company.name:
                    mes += u"Не указано наименование компании.\n"
                if not company.okpo:
                    mes += u"Не указано ОКПО компании.\n"
                if not company.inn:
                    mes += u"Не указан ИНН компании.\n"
                else:
                    if len(company.inn) == 12:
                        if not company.partner_id.last_name_IP:
                            mes += u"Не указана фамилия ИП для вашей компании.\n"
                        if not company.partner_id.first_name_IP:
                            mes += u"Не указано имя ИП для вашей компании.\n"
                        if not company.partner_id.middle_name_IP:
                            mes += u"Не указано отчество ИП для вашей компании.\n"
                    elif len(company.inn) == 10:
                        if not company.kpp:
                            mes += u"Не указан КПП компании.\n"
                    else:
                        mes += u"Некорректный ИНН компании.\n"
                if not company.city:
                    mes += u"Не указан город компании.\n"
                if not company.street:
                    mes += u"Не указан адрес компании.\n"
                if not company.chief_id:
                    mes += u"Не указан руководитель компании.\n"
                else:
                    if not company.chief_id.function:
                        mes += u"Не указана должность руководителя компании.\n"
                    if not company.chief_id.last_name:
                        mes += u"Не указана фамилия руководителя компании.\n"
                    if not company.chief_id.first_name:
                        mes += u"Не указано имя руководителя компании.\n"
                    if not company.chief_id.second_name:
                        mes += u"Не указано отчество руководителя компании.\n"
            pid = s.partner_id.parent_id
            if not pid:
                pid = s.partner_id
            if not pid:
                mes += u"Не указан контрагент.\n"
            else:
                if not pid.edi:
                    mes += u"Не указан идентификатор контрагента для Diadoc.\n"
                if not pid.name:
                    mes += u"Не указано наименование контрагента.\n"
                if not pid.okpo:
                    mes += u"Не указано ОКПО контрагента.\n"
                if not pid.inn:
                    mes += u"Не указан ИНН контрагента.\n"
                else:
                    if len(pid.inn) == 12:
                        if not pid.last_name_IP:
                            mes += u"Не указана фамилия ИП для контрагента.\n"
                        if not pid.first_name_IP:
                            mes += u"Не указано имя ИП для контрагента.\n"
                        if not pid.middle_name_IP:
                            mes += u"Не указано отчество ИП для контрагента.\n"
                    elif len(pid.inn) == 10:
                        if not pid.kpp:
                            mes += u"Не указан КПП контрагента.\n"
                    else:
                        mes += u"Некорректный ИНН контрагента.\n"
                if not pid.city:
                    mes += u"Не указан город контрагента.\n"
                if not pid.street:
                    mes += u"Не указан адрес контрагента.\n"
            if manually:
                if not s.edi:
                    mes += u"Не указан идентификатор документа для Diadoc.\n"
                if not s.name:
                    mes += u"Не указано наименование документа\n"
                if not s.invoice_date:
                    mes += u"Не указана дата документа\n"
            if not s.only_service:
                gruzootpr = s.gruzootpr
                if not gruzootpr:
                    gruzootpr = pid
                if gruzootpr.parent_id:
                    gruzootpr = gruzootpr.parent_id
                if not gruzootpr:
                    mes += u"Не указан грузоотправитель.\n"
                else:
                    if not gruzootpr.name:
                        mes += u"Не указано наименование грузоотправителя.\n"
                    if not gruzootpr.okpo:
                        mes += u"Не указано ОКПО грузоотправителя.\n"
                    if not gruzootpr.inn:
                        mes += u"Не указан ИНН грузоотправителя.\n"
                    else:
                        if len(gruzootpr.inn) == 12:
                            if not gruzootpr.last_name_IP:
                                mes += u"Не указана фамилия ИП для грузоотправителя.\n"
                            if not gruzootpr.first_name_IP:
                                mes += u"Не указано имя ИП для грузоотправителя.\n"
                            if not gruzootpr.middle_name_IP:
                                mes += u"Не указано отчество ИП для грузоотправителя.\n"
                        elif len(gruzootpr.inn) == 10:
                            if not gruzootpr.kpp:
                                mes += u"Не указан КПП грузоотправителя.\n"
                        else:
                            mes += u"Некорректный ИНН грузоотправителя.\n"
                    if not gruzootpr.city:
                        mes += u"Не указан город грузоотправителя.\n"
                    if not gruzootpr.street:
                        mes += u"Не указан адрес грузоотправителя.\n"
                gruzopol = s.gruzopol
                if not gruzopol:
                    gruzopol = pid
                if gruzopol.parent_id:
                    gruzopol = gruzopol.parent_id
                if not gruzopol:
                    mes += u"Не указан грузополучатель.\n"
                else:
                    if not gruzopol.name:
                        mes += u"Не указано наименование грузополучателя.\n"
                    if not gruzopol.okpo:
                        mes += u"Не указано ОКПО грузополучателя.\n"
                    if not gruzopol.inn:
                        mes += u"Не указан ИНН грузополучателя.\n"
                    else:
                        if len(gruzopol.inn) == 12:
                            if not gruzopol.last_name_IP:
                                mes += u"Не указана фамилия ИП для грузополучателя.\n"
                            if not gruzopol.first_name_IP:
                                mes += u"Не указано имя ИП для грузополучателя.\n"
                            if not gruzopol.middle_name_IP:
                                mes += u"Не указано отчество ИП для грузополучателя.\n"
                        elif len(gruzopol.inn) == 10:
                            if not gruzopol.kpp:
                                mes += u"Не указан КПП грузополучателя.\n"
                        else:
                            mes += u"Некорректный ИНН грузополучателя.\n"
                    if not gruzopol.city:
                        mes += u"Не указан город грузополучателя.\n"
                    if not gruzopol.street:
                        mes += u"Не указан адрес грузополучателя.\n"
            if s.payment_num:
                if not s.payment_date:
                    mes += u"Не указана дата платежки в УПД.\n"
            if not s.invoice_line_ids:
                mes += u"Отсутствуют строки заказа.\n"
            else:
                for line in s.invoice_line_ids:
                    if not line.price_unit:
                        mes += u"Не указана цена за единицу для товара {}.\n".format(line.name)
                    if not line.quantity:
                        mes += u"Не указано количество для товара {}.\n".format(line.name)
                    if not line.product_uom_id.okei:
                        mes += u"Не указан код ОКЕИ для единицы измерения {}.\n".format(line.product_uom_id.name)
            if not s.mt_contract_id:
                mes += u"Не указан договор.\n"
            else:
                if not s.mt_contract_id.name:
                    mes += u"Не указано наименование договора.\n"
                if not s.mt_contract_id.date_start:
                    mes += u"Не указана дата договора.\n"
            if not s.kladov:
                mes += u"Не указано лицо, ответственное за передачу товаров/услуг.\n"
            else:
                if not s.kladov.partner_id.function:
                    mes += u"Не указана должность лица, ответственного за передачу товаров/услуг.\n"
            return str(mes)
