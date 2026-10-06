from odoo import api, fields, models, exceptions
from datetime import datetime


class contract_sale_order(models.Model):
    _inherit = 'sale.order'
    mt_contractid = fields.Many2one('partner.contract.customer', string='Номер договора')
    sec_partner_id = fields.Many2one('res.partner', string='Контрагент', store=True, compute='get_pid')
    stamp = fields.Boolean(string='Печать и подпись', related='mt_contractid.stamp')

    @api.depends('partner_id')
    def get_pid(self):
        for s in self:
            s.sec_partner_id = s.partner_id.parent_id if s.partner_id.parent_id else s.partner_id

    @api.onchange('mt_contractid')
    def set_ons(self):
        for s in self:
            if s.mt_contractid:
                s.payment_term_id = s.mt_contractid.payment_term_id

    @api.constrains('state')
    def late_payment_check(self):
        for s in self:
            if s.mt_contractid:
                if s.state == 'sale':
                    late_invoices_count = 0
                    max_receivable = s.mt_contractid.profile_id.max_receivable_id  # макс. деб. задолженность в договоре
                    # ищу просроченные инвойсы контрагента указанного в заказе со стейтом "Подтверждено"
                    invoices_obj = self.env['account.move'].search([('partner_id', '=', s.partner_id.id),
                                                                    ('state', '=', 'posted'),
                                                                    ('payment_state', 'not in', ['paid','reversed']),
                                                                    ('move_type','in',['out_invoice']),
                                                                    ('invoice_date_due', '<', datetime.now().date())])

                    for invoice in invoices_obj:
                        late_invoices_count += invoice.amount_residual  # складываю деб. задолженность по просроченным инвойсам

                    if late_invoices_count > max_receivable:
                        raise exceptions.ValidationError(
                            f'Нельзя подтвердить заказ, так как у контрагента {s.sec_partner_id.name} нарушено '
                            f'условие по дебиторской задолженности.\n\n'
                            f'Контрагент {s.sec_partner_id.name} должен {late_invoices_count}руб.\n'
                            f'Максимальная дебиторская задолженность указанная в '
                            f'договоре №{s.mt_contractid.name} - {max_receivable}руб.\n\n'
                            f'Проверьте следующие неоплаченные счета контрагента:\n'
                            f'{", ".join([invoice.name for invoice in invoices_obj])}')

    # def _get_invoice_grouping_keys(self):
    #     res = super(contract_sale_order, self)._get_invoice_grouping_keys()
    #     res.append('mt_contractid')
    #     return res

    def _prepare_invoice(self):
        invoice_vals = super(contract_sale_order, self)._prepare_invoice()
        for s in self:
            if s.mt_contractid:
                invoice_vals['mt_contractid'] = s.mt_contractid.id
                invoice_vals['osnovanie'] = 'Договор № ' + s.mt_contractid.name + ' от ' + fields.Datetime.from_string(
                    s.mt_contractid.date_start).strftime("%d.%m.%Y")
        return invoice_vals


class ContractCreateInvoice(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    def _prepare_invoice_values(self, order, so_lines):
        invoice_vals = super(ContractCreateInvoice, self)._prepare_invoice_values(order, so_lines)
        if order.mt_contractid:
            invoice_vals['mt_contractid'] = order.mt_contractid.id
            invoice_vals['osnovanie'] = 'Договор № ' + order.mt_contractid.name + ' от ' + fields.Datetime.from_string(order.mt_contractid.date_start).strftime("%d.%m.%Y")
        return invoice_vals

class contract_invoice(models.Model):
    _inherit = 'account.move'
    mt_contractid = fields.Many2one('partner.contract.customer', string='Номер договора')
    sf_number = fields.Char(string='Номер с/ф')
    osnovanie = fields.Char(string='Основание')
    sec_partner_id = fields.Many2one('res.partner', string='Контрагент', store=True, compute='get_pid')
    stamp = fields.Boolean(string='Печать и подпись', related='mt_contractid.stamp')

    @api.depends('partner_id')
    def get_pid(self):
        for s in self:
            s.sec_partner_id = s.partner_id.parent_id if s.partner_id.parent_id else s.partner_id

    @api.onchange('mt_contractid')
    def set_ons(self):
        if self.mt_contractid:
            self.osnovanie = 'Договор № ' + self.mt_contractid.name + ' от ' + fields.Datetime.from_string(
                self.mt_contractid.date_start).strftime("%d.%m.%Y")

    @api.constrains('state')
    def invoice_fields_check(self):
        for s in self:
            if s.state == 'posted':
                if s.mt_contractid:
                    errors_list = []
                    journal_in_contract = s.mt_contractid.profile_id.journal_id
                    payment_term_in_contract = s.mt_contractid.profile_id.payment_term_id
                    receivable_in_contract = s.mt_contractid.profile_id.receivable_account_id

                    if journal_in_contract != s.journal_id:
                        errors_list.append(f'Отличается Журнал - [{s.journal_id.name}] '
                                           f'и указанный в договоре №{s.mt_contractid.name} '
                                           f'Журнал - [{journal_in_contract.name}]\n\n')

                    if payment_term_in_contract != s.invoice_payment_term_id:
                        errors_list.append(f'Отличается поле "Условие оплаты" в инвойсе '
                                           f'[Условие оплаты - {s.invoice_payment_term_id.name}] '
                                           f'и указанный в договоре №{s.mt_contractid.name} '
                                           f'[Условие оплаты - {payment_term_in_contract.name}]\n\n')

                    if receivable_in_contract not in s.line_ids.account_id:
                        errors_list.append(f'Отличается поле "Счет дебиторской задолженности" в инвойсе '
                                           f'и указанный в договоре №{s.mt_contractid.name}')

                    if errors_list:
                        raise exceptions.ValidationError(''.join(errors_list))


class contact_purchase_order(models.Model):
    _inherit = 'purchase.order'
    mt_contractid = fields.Many2one('partner.contract.customer', string='Номер договора')
    sec_partner_id = fields.Many2one('res.partner', string='Контрагент', store=True, compute='get_pid')

    @api.depends('partner_id')
    def get_pid(self):
        for s in self:
            s.sec_partner_id = s.partner_id.parent_id if s.partner_id.parent_id else s.partner_id
