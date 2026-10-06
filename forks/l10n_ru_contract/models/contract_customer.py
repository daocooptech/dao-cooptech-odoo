# -*- coding: utf-8 -*-
from odoo import api, fields, models, exceptions, tools, _
import pymorphy3
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from .crutch_fields_header import IP_CONTACT_HEADER, ENTITY_CONTRACT_HEADER, INDIVIDUAL_CONTRACT_HEADER
from odoo.exceptions import UserError
import re
import base64
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH


class PartnerContractCustomer(models.Model):
    _name = 'partner.contract.customer'
    _description = 'partner.contract.customer'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'mail.render.mixin']

    def get_dateend(self):
        for s in self:
            if s.date_start:
                six_months = fields.Datetime.from_string(s.date_start) + relativedelta(months=+11)
            else:
                six_months = datetime.today() + relativedelta(months=+11)
            return fields.Datetime.to_string(six_months)

    name = fields.Char(string='Номер')
    date_start = fields.Date(string='Дата договора', required=True, default=fields.Datetime.now())
    partner_id = fields.Many2one('res.partner', string='Контрагент', required=True)
    sec_partner_id = fields.Many2one('res.partner', string='Контрагент как в заказе')
    company_id = fields.Many2one('res.company', string='Компания', required=True)
    name_print = fields.Char(string='Имя для печати', compute='_get_name_print')
    name_print1 = fields.Char(string='Имя для печати, И.П.', compute='_get_name_printip')
    date_end = fields.Date(string='Дата окончания', required=True, default=get_dateend)
    name_dirprint = fields.Char(string='Имя нашего директора для печати')
    name_dirprint1 = fields.Char(string='Имя нашего директора для печати И.П.')
    lines = fields.One2many('contract.line', 'contract_id', string='Договорные цены')
    type = fields.Selection(
        [('customer', 'С покупателем'),
         ('supplier', 'С поставщиком'),
         ('other', 'Прочие расчеты'),

         ],
        string='Тип договора', default='customer', required=True)
    saleorder_id = fields.Many2one('sale.order', string='Заказ/Сделка')
    stamp = fields.Boolean(string='Печать и подпись')
    signed = fields.Boolean(string='Договор подписан')
    state = fields.Selection(
        [('draft', 'Черновик'),
         ('progress', 'На согласовании'),
         ('signed', 'Подписан, действует'),
         ('closed', 'Истёк'),
         ],
        string='Статус', default='draft', group_expand='_expand_states', index=True
    )
    is_template = fields.Boolean('Это шаблон')
    copy_from = fields.Many2one('partner.contract.customer', string='Копировать из этого шаблона')
    profile_id = fields.Many2one('contract.profile', string='Вид договора', required=True)
    credit_limit = fields.Float(string='Лимит кредита')
    guid_1s = fields.Char('Код договора из 1С')
    buh_code = fields.Char('Код договора из бухгалтерии')
    payment_term_id = fields.Many2one('account.payment.term', string='Условие оплаты')
    manager_id = fields.Many2one('res.users', string='Менеджер по продажам')
    accountant_id = fields.Many2one('res.users', string='Бухгалтер по взаиморасчетам')
    time_to_delivery_from = fields.Datetime('Время доставки от')
    time_to_delivery_to = fields.Datetime('Время доставки до')
    day_of_delivery = fields.Float('Дни доставки')
    day_of_otgruzki = fields.Float('Дни отгрузки')

    channel_id = fields.Many2one('saleorder.channel', string='Канал продаж')
    team_id = fields.Many2one('crm.team', string='Команда продаж')
    order_days_ids = fields.Many2many(comodel_name='contract.day', relation='orderdays', string='Дни доставки',
                                      column1='contract_id', column2='day_id')
    shipment_days_ids = fields.Many2many(comodel_name='contract.day', relation='shipmentdays', string='Дни отгрузки',
                                         column1='contract_id',
                                         column2='day_id')
    # Доработка хедера договора
    partner_type = fields.Selection(string='Тип контрагента', selection=[
        ('person', 'Физ. лицо'),
        ('company_ip', 'ИП'),
        ('company', 'Юр. лицо')
    ], required=True)
    contract_header = fields.Html('Шапка договора')

    @api.onchange('partner_type')
    def generate_contract_header(self):
        self.ensure_one()
        self.render_model = 'partner.contract.customer'
        if self.partner_type == 'company_ip':
            self.contract_header = IP_CONTACT_HEADER
        elif self.partner_type == 'person':
            self.contract_header = INDIVIDUAL_CONTRACT_HEADER
        else:
            self.contract_header = ENTITY_CONTRACT_HEADER
        # # Рендер Jinja выражение типа {{object.field}}
        result = self._render_template(self.contract_header, self.render_model, res_ids=[self.id])
        result = tools.html_sanitize(result[self.id])
        self.contract_header = result

    @api.onchange('sec_partner_id')
    def set_pid(self):
        for s in self:
            s.partner_id = s.sec_partner_id.parent_id if s.sec_partner_id.parent_id else s.sec_partner_id

    def _expand_states(self, states, domain, order):
        return [key for key, val in type(self).state.selection]

    def copy_it(self):
        for s in self:
            if s.copy_from:
                for line in s.copy_from.lines:
                    line.copy({'contract_id': s.id})

    def _get_name_print(self):
        morph = pymorphy3.MorphAnalyzer()
        for s in self:
            s.name_print = False
            director = self.env['res.partner'].search([('parent_id', '=', s.partner_id.id), ('type', '=', 'director')],
                                                      limit=1)
            if director:
                if len(director.name.split(' ')) == 3:
                    lastname_old, firstname_old, middlename_old = director.name.split(' ')

                    if lastname_old:
                        lastname_n = morph.parse(lastname_old)[0]
                        if lastname_n.inflect({'gent'}):
                            lastname_n = lastname_n.inflect({'gent'}).word
                        else:
                            lastname_n = lastname_old
                    else:
                        lastname_n = ''

                    if firstname_old:
                        firstname_n = morph.parse(firstname_old)[0]
                        firstname_n = firstname_n.inflect({'gent'}).word
                    else:
                        firstname_n = ''

                    if middlename_old:
                        middlename_n = morph.parse(middlename_old)[0]
                        middlename_n = middlename_n.inflect({'gent'}).word
                    else:
                        middlename_n = ''

                    name_print = lastname_n + ' ' + firstname_n + ' ' + middlename_n

                    s.name_print = name_print.title()

    def _get_name_print1(self):
        morph = pymorphy3.MorphAnalyzer()
        for s in self:
            director = s.company_id.chief_id.partner_id if s.company_id.chief_id else False
            # raise exceptions.UserError(str(director))
            s.name_dirprint = False
            if director:
                if len(director.name.split(' ')) == 3:
                    lastname_old, firstname_old, middlename_old = director.name.split(' ')

                    if lastname_old:
                        lastname_n = morph.parse(lastname_old)[0]
                        lastname_n = lastname_n.inflect({'gent'}).word
                    else:
                        lastname_n = ''

                    if firstname_old:
                        firstname_n = morph.parse(firstname_old)[0]
                        firstname_n = firstname_n.inflect({'gent'}).word
                    else:
                        firstname_n = ''

                    if middlename_old:
                        middlename_n = morph.parse(middlename_old)[0]
                        middlename_n = middlename_n.inflect({'gent'}).word
                    else:
                        middlename_n = ''

                    name_print = lastname_n + ' ' + firstname_n + ' ' + middlename_n

                    s.name_dirprint = name_print.title()

    @api.model
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        records = super().create(vals_list)

        for record, vals in zip(records, vals_list):
            if vals.get('is_template'):
                continue
            if vals.get('type') == 'customer':
                sequence_code = 'partner.contract.customer.sequence'
            elif vals.get('type') == 'supplier':
                sequence_code = 'partner.contract.supplier.sequence'
            else:
                continue
            name = self.env['ir.sequence'].next_by_code(sequence_code)
            record.name = name

        return records

    # @api.model
    def write(self, values):

        if 'state' in values:
            if self.state != values['state']:
                msg = 'Статус: ' + dict(self._fields['state'].selection).get(self.state) + ' -> ' + dict(
                    self._fields['state'].selection).get(values['state'])
                self.message_post(body=msg)
        res = super(PartnerContractCustomer, self).write(values)
        return res

    def _get_name_print1ip(self):
        for s in self:
            s.name_dirprint1 = s.company_id.chief_id.partner_id.name if s.company_id.chief_id else False

    def _get_name_printip(self):
        for s in self:
            s.name_print1 = False
            director = self.env['res.partner'].search([('parent_id', '=', s.partner_id.id), ('type', '=', 'director')],
                                                      limit=1)
            if director:
                s.name_print1 = director.name

    def print_supp(self):
        # self.filtered(lambda s: s.state == 'draft').write({'state': 'sent'})
        return self.env['report'].get_action(self, 'mta_base.action_mtacontractsupp_report')

    def print_contract_cust(self):
        for s in self:
            if s.saleorder_id:
                return s.saleorder_id.print_contract()
            else:
                raise exceptions.UserError(
                    'Вы не можете напечатать договор с Клиентом, потому что нет связи с Заказом. Нужно зайти в Заказ и привязать этот договор.')

    def contract_action_confirm(self):
        for s in self:
            if s.state == 'draft':
                s.state = 'progress'
            elif s.state == 'progress':
                s.state = 'signed'

    def contract_in_draft(self):
        for s in self:
            s.state = 'draft'

    @api.onchange('name')
    def set_comp_and_partn(self):
        for s in self:
            context = s.env.context
            order_id = context.get('sale_order_id')
            if order_id:
                sale_order = self.env['sale.order'].browse(order_id)

                s.company_id = sale_order.company_id
                s.partner_id = sale_order.partner_id

    @api.onchange('profile_id')
    def set_payment(self):
        for s in self:
            if s.profile_id.payment_term_id:
                s.payment_term_id = s.profile_id.payment_term_id

    # @api.constrains('name')
    def check_name(self):
        obj = self.search([('name', '=', self.name), ('id', '!=', self.id), ('state', '!=', 'closed')])
        if obj:
            raise exceptions.ValidationError('Договор с таким номером уже существует')

    """
    @api.constrains('profile_id')
    def check_profile_id(self):
        contracts = self.search([('partner_id', '=', self.partner_id.id), ('id', '!=', self.id)])
        if contracts:
            profiles_in_contracts = contracts.profile_id
            #  raise exceptions.ValidationError(profiles_in_contracts.ids)
            if profiles_in_contracts:
                ads = self.env['contract.allowed.profiles'].search(
                    [('allowed_profiles', 'in', profiles_in_contracts.ids)])
                if ads:
                    raise exceptions.ValidationError((self.profile_id.name, ads.name))
        #  raise exceptions.ValidationError(contracts)
    """


    def action_report_contract_with_format(self, report_format):
        if report_format == 'docx':
            file_data, filename = self._generate_contract_docx()
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif report_format == 'md':
            file_data, filename = self._generate_contract_md()
            mimetype = 'application/md'
        else:
            raise UserError("Неверный формат отчёта.")

        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'raw': file_data,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': mimetype or 'application/octet-stream',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }

    def _strip_html_tags(self, html):
        clean = re.compile('<.*?>')
        return re.sub(clean, '', html)

    def _generate_contract_docx(self):
        doc = Document()
        style = doc.styles['Normal']
        font = style.font
        font.name = 'Times New Roman'
        font.size = Pt(12)
        company = self.env.company
        partner = self.partner_id

        table_header = doc.add_table(rows=1, cols=2)
        rc_header = table_header.rows[0].cells
        run_left = rc_header[0].paragraphs[0].add_run(f"{company.name or ''}")
        run_left.font.bold = True
        header_paragraph_right = rc_header[1].paragraphs[0]
        header_paragraph_right.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        header_run_right = header_paragraph_right.add_run(f"Договор {self.name or ''} от {self.date_start or ''}")
        header_run_right.font.bold = True

        header_paragraph_centre = doc.add_paragraph(f"Договор №{self.name or ''} от {self.date_start or ''}\n на поставку продукции")
        header_paragraph_centre.alignment = WD_ALIGN_PARAGRAPH.CENTER

        table_city_date = doc.add_table(rows=1, cols=2)
        row = table_city_date.rows[0].cells
        run_city = row[0].paragraphs[0].add_run(company.city or '')
        run_city.font.bold = True
        paragraph_date = row[1].paragraphs[0]
        paragraph_date.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run_date = paragraph_date.add_run(self.get_date_text(self.date_start) or '')
        run_date.font.bold = True

        text_contract_header = self._strip_html_tags(self.contract_header)
        doc.add_paragraph(text_contract_header)

        for line in self.lines.sorted(key=lambda r: r.sequence, reverse=False):
            doc.add_paragraph(line.name or '')
            doc.add_paragraph(line.punct or '')

        doc.add_paragraph("Реквизиты и подписи сторон.").alignment = WD_ALIGN_PARAGRAPH.CENTER

        table = doc.add_table(rows=7, cols=6)
        table.style = 'Table Grid'
        table.cell(0, 0).merge(table.cell(0, 2)).text = "Поставщик:"
        table.cell(0, 3).merge(table.cell(0, 5)).text = "Покупатель:"
        table.cell(1, 0).merge(table.cell(1, 2)).text = company.name or ''
        table.cell(1, 3).merge(table.cell(1, 5)).text = partner.name or ''
        table.cell(2, 0).merge(table.cell(2, 2)).text = f"ИНН {company.inn or ''}"
        table.cell(2, 3).merge(table.cell(2, 5)).text = f"ИНН {partner.inn or ''}"
        table.cell(3, 0).merge(table.cell(3, 1)).text = f"ОГРН {company.partner_id.ogrn or ''}"
        table.cell(3, 3).merge(table.cell(3, 5)).text = f"ОГРН {partner.ogrn or ''}"
        table.cell(4, 0).merge(table.cell(4, 2)).text = f"КПП {company.kpp or ''}"
        table.cell(4, 3).merge(table.cell(4, 5)).text = f"КПП {partner.kpp or ''}"
        company_address = self.address(company) or ''
        partner_address = self.address(partner) or ''
        table.cell(5, 0).merge(table.cell(5, 2)).text = f"Юридический адрес: {company_address}"
        table.cell(5, 3).merge(table.cell(5, 5)).text = f"Юридический адрес: {partner_address}"
        table.cell(6, 0).merge(table.cell(6, 2)).text = "Подпись Исполнителя:"
        table.cell(6, 3).merge(table.cell(6, 5)).text = "Подпись Заказчика:"

        f = BytesIO()
        doc.save(f)
        f.seek(0)
        return f.read(), 'Договор (DOCX).docx'


    def _generate_contract_md(self):
        company = self.env.company
        partner = self.partner_id

        lines = []

        lines.append(f"| **{company.name or ''}** | **Договор {self.name or ''} от {self.date_start or ''}** |")
        lines.append("| --- | --- |")

        lines.append(f"**Договор {self.name or ''} от {self.date_start or ''}**\n")
        lines.append("**на поставку продукции**\n")

        lines.append("| Город | Дата |")
        lines.append("| --- | --- |")
        lines.append(f"| {company.city or ''} | {self.get_date_text(self.date_start)} |\n")

        text_contract_header = self._strip_html_tags(self.contract_header or "")
        lines.append(text_contract_header + "\n")

        for line in self.lines.sorted(key=lambda r: r.sequence):
            lines.append(f"**{line.name or ''}**")
            lines.append((line.punct or '') + "\n")

        lines.append("**Реквизиты и подписи сторон.**\n")

        lines.append("| Поставщик | | Покупатель | |")
        lines.append("| --- | --- | --- | --- |")

        lines.append(f"| {company.name or ''} | | {partner.name or ''} | |")
        lines.append(f"| ИНН {company.inn or ''} | | ИНН {partner.inn or ''} | |")

        lines.append(f"| ОГРН {company.ogrn or ''} | | ОГРН {partner.ogrn or ''} | |")
        lines.append(f"| КПП {company.kpp or ''} | | КПП {partner.kpp or ''} | |")

        company_address = self.address(company) or ''
        partner_address = self.address(partner) or ''
        lines.append(f"| Юридический адрес: {company_address} | | Юридический адрес: {partner_address} | |")
        lines.append(f"| Подпись Исполнителя | | Подпись Заказчика | |\n")

        md_content = "\n".join(lines)
        return md_content.encode('utf-8'), 'Договор (MD).md'

    def action_print_by_template(self):
        return {
            'name': 'Печать по шаблону',
            'type': 'ir.actions.act_window',
            'res_model': 'report.template.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_contract_id': self.id},
        }

class Partner(models.Model):
    _inherit = 'res.partner'

    contract_count = fields.Integer(string='Договоры', compute='get_count_contract')
    pol = fields.Selection(string="Пол", selection=[('m', 'Муж.'), ('j', 'Жен'), ], required=False)
    type = fields.Selection(selection_add=[('director', 'Директор')])

    def get_count_contract(self):
        contract = self.env['partner.contract.customer']
        self.contract_count = contract.search_count([('partner_id', '=', self.id)])

    def action_view_contract(self):
        action = self.env.ref('contract.contract_customer_action').read()[0]

        action['domain'] = [('partner_id', '=', self.id)]

        return action


class ContractLine(models.Model):
    _name = 'contract.line'
    _description = 'contract.line'
    contract_id = fields.Many2one('partner.contract.customer', string='Order Reference', required=True,
                                  ondelete='cascade', index=True, copy=False)
    _order = "sequence desc"
    # name = fields.Text(string='Название для договора')
    # price_unit = fields.Float('Цена', default=0.0)
    # product_uom = fields.Many2one('uom.uom', string='Единица измерения')
    # product_id = fields.Many2one('product.product', string='Услуга', domain=[('sale_ok', '=', True)], change_default=True, ondelete='restrict')
    sequence = fields.Integer('Порядок')
    name = fields.Char('Номер пункта')
    punct = fields.Html('Текст пункта')

    @api.onchange('product_id')
    def set_name(self):
        for s in self:
            s.name = s.product_id.name


class AllowedProfiles(models.Model):
    _name = 'contract.allowed.profiles'
    _description = 'contract.allowed.profiles'
    name = fields.Char(string='Одновременно включены следующие виды договоров:')
    allowed_profiles = fields.Many2many('contract.profile', string='Виды договоров', required=True)

    @api.onchange('allowed_profiles')
    def set_name(self):
        for s in self:
            s.name = ''
            for profile in s.allowed_profiles:
                s.name += profile.name + ' + '
            if s.name:
                if s.name[-2] == '+':
                    s.name = s.name[:-2]


class ContractProfile(models.Model):
    _name = 'contract.profile'
    _description = 'contract.profile'
    name = fields.Char(string='Вид договора', required=True)
    payable_account_id = fields.Many2one('account.account', string='Счет кредиторской задолженности', required=True)
    receivable_account_id = fields.Many2one('account.account', string='Счет дебиторской задолженности', required=True)
    max_receivable_id = fields.Float(string='Максимальная деб. задолженность', required=True)
    payment_term_id = fields.Many2one('account.payment.term', string='Условие оплаты', required=True)
    journal_id = fields.Many2one('account.journal', string='Журнал', required=True)


class ContractDay(models.Model):
    _name = 'contract.day'
    _description = 'contract.day'
    name = fields.Char('День')
