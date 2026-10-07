from datetime import datetime
from odoo import api, fields, models

class AccountInvoice(models.Model):
    _inherit = 'account.move'
    kladov=fields.Many2one('res.users', string='Ответственный за передачу товаров/услуг')
    gruzopol=fields.Many2one('res.partner', string='Грузополучатель')
    gruzootpr=fields.Many2one('res.partner', string='Грузоотправитель')
    transport=fields.Char('Данные о транспортировке и грузе')
    osnovanie=fields.Char('Основание')
    payment_text=fields.Char('Текст для платежек в УПД', compute='_compute_get_txtpayment')
    payment_num=fields.Char('Номер платежки в УПД', compute='_compute_get_txtpayment')
    payment_date = fields.Char('Дата платежки в УПД', compute='_compute_get_txtpayment')
    only_service = fields.Boolean('Только услуги', compute='_compute_get_check_service')

    @api.depends('invoice_line_ids')
    def _compute_get_check_service(self):
        for s in self:
            s.only_service = all((line.product_id.type=='service') for line in s.invoice_line_ids)

    def _compute_get_txtpayment(self):
        for s in self:
            payments = s._get_reconciled_payments()
            payment_text = ''

            for payment in payments:
                if payment.date:
                    payment_text += payment.name + ' от ' + \
                                    fields.Datetime.from_string(payment.date).strftime("%d.%m.%Y")
                if payments[-1]!=payment:
                    payment_text += ', '
            if payments:
                s.payment_num = payments[0].name
                s.payment_date = fields.Datetime.from_string(payments[0].date).strftime("%d.%m.%Y")
            else:
                s.payment_num = ''
                s.payment_text = ''
                s.payment_date = ''

            s.payment_text = payment_text

    # def action_bill_sent(self):
    #     assert len(self) == 1, 'This option should only be used for a single id at a time.'
    #     template = self.env.ref('account.email_template_edi_invoice', False)
    #     compose_form = self.env.ref('mail.email_compose_message_wizard_form', False)
    #     ctx = {
    #         'default_model': 'account.move',
    #         'default_res_id': self.id,
    #         'default_use_template': bool(template),
    #         'default_template_id': template.id,
    #         'default_composition_mode': 'comment',
    #         'mark_invoice_as_sent': True,
    #     }
    #     return {
    #         'name': 'Compose Email',
    #         'type': 'ir.actions.act_window',
    #         'view_type': 'form',
    #         'view_mode': 'form',
    #         'res_model': 'mail.compose.message',
    #         'views': [(compose_form.id, 'form')],
    #         'view_id': compose_form.id,
    #         'target': 'new',
    #         'context': ctx,
    #     }

    def bill_print(self):
        assert len(self) == 1, 'This option should only be used for a single id at a time.'
        return self.env['report'].get_action(self, 'l10n_ru_doc.report_upd')

    def get_delivery_doc_name(self):
        for s in self:
            if s:
                pickings = []
                pickings_list = '0'
                orders = self.env['sale.order'].sudo().search([('name','=',s.invoice_origin)]) if s.invoice_origin else []
                for o in orders:
                    if o.picking_ids:
                        for p in o.picking_ids:
                            pickings.append(p.name)
                if len(pickings)>0:
                    pickings_list = ';'.join(pickings)
                if pickings_list != '0':
                    return pickings_list
                if s.name and s.name.find('/') > -1:
                    return 'УПД № ' + s.name[len(s.name) - 4:]
                return 'УПД № ' + str(s.name) if s.name else ''
            

    def get_delivery_doc_date(self):
        for s in self:
            if s:
                delivery_dates = []
                pickings = []
                orders = self.env['sale.order'].sudo().search([('name', '=', s.invoice_origin)])
                for o in orders:
                    if o.picking_ids:
                        for p in o.picking_ids:
                            if p.date_done:
                                formatted_date = datetime.strftime(p.date, '%d.%m.%Y')
                                pickings.append(formatted_date)
                if pickings and len(pickings)>0:
                    delivery_dates.append(';'.join(pickings))
                else:
                    if s.date:
                        delivery_dates.append(datetime.strftime(s.date, '%d.%m.%Y'))
                return delivery_dates

    def get_function_partner(self, partner=False, type='director'):
        if partner:
            if partner.parent_id:
                partner = partner.parent_id
            director = self.env['res.partner'].search([('parent_id', '=', partner.id),
                                                       ('type', '=', type)], limit=1)
            if director:
                if director.function:
                    return director.function
        return ''

    def get_name_partner(self, partner=False, type='director'):
        if partner:
            if partner.parent_id:
                partner = partner.parent_id
            director = self.env['res.partner'].search([('parent_id', '=', partner.id),
                                                       ('type', '=', type)], limit=1)
            if director:
                if director.name:
                    return director.name
        return ''

    def get_facsimile_partner(self, partner=False, type='director'):
        if partner:
            if partner.parent_id:
                partner = partner.parent_id
            director = self.env['res.partner'].search([('parent_id', '=', partner.id),
                                                       ('type', '=', type)],
                                                      limit=1)
            if director:
                if director.facsimile:
                    return director.facsimile
        return ''

    def get_stamp_partner(self, partner=False):
        if partner:
            if partner.parent_id:
                partner = partner.parent_id
            if partner.stamp:
                return partner.stamp
        return False


