# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import models, fields, api


class AccountPaymentRegisterPrepaid(models.TransientModel):
    _name = 'payment.register.prepaid'
    _description = 'Регистрация авансовых платежей'

    company_id = fields.Many2one(comodel_name='res.company', string='Компания')
    payment_method_line_id = fields.Many2one(comodel_name='account.payment.method.line', string='Метод оплаты', required=True)
    partner_bank_id = fields.Many2one(comodel_name='res.partner.bank', string="Банковский счёт получателя")
    amount = fields.Monetary(currency_field='currency_id', string='Сумма', readonly=False, required=True)
    currency_id = fields.Many2one(comodel_name='res.currency', string='Валюта', required=True)
    payment_date = fields.Date(string="Дата платежа", required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(comodel_name='account.journal', string='Журнал', required=True)
    communication = fields.Char(string="Заметки")
    prepaid_id = fields.Many2one(comodel_name='order.prepaid', string="Авансовый платеж")
    advance_type = fields.Selection(
                                    string='Тип счета на аванс', related='prepaid_id.advance_type')
    method_line_type = fields.Many2one(comodel_name='account.payment.method.line', string="Метод")
    amount_const = fields.Float(string='Сумма(Const)')
    currency_const = fields.Many2one(comodel_name='res.currency', string='Валюта(Const)')

    @api.onchange('partner_bank_id', 'journal_id')
    def currency_bank(self):
        if self.partner_bank_id:
            self.currency_id = self.partner_bank_id.currency_id

    @api.onchange('currency_id')
    def _amount(self):
        for wizard in self:
            if not wizard.journal_id or not wizard.currency_id or not wizard.payment_date:
                wizard.amount = wizard.amount
            else:
                test = self.prepaid_id.currency_id._convert(
                    self.amount_const,
                    self.currency_id,
                    self.company_id,
                    self.payment_date,
                )
                wizard.amount = test

    @api.onchange('journal_id')
    def _payment_method_line_id(self):
        journal = self.journal_id
        if journal:
            if self.advance_type == 'outbound':
                self.payment_method_line_id = journal.inbound_payment_method_line_ids[0] if journal.inbound_payment_method_line_ids else False
            elif self.advance_type == 'inbound':
                self.payment_method_line_id = journal.outbound_payment_method_line_ids[0] if journal.outbound_payment_method_line_ids else False
            else:
                self.payment_method_line_id = False
        else:
            self.payment_method_line_id = False

    @api.onchange('journal_id')
    def _bank(self):
        if self.prepaid_id and self.prepaid_id.partner_bank_id:
            self.partner_bank_id = self.prepaid_id.partner_bank_id
        elif self.journal_id and self.journal_id.bank_account_id:
            self.partner_bank_id = self.journal_id.bank_account_id
        else:
            self.partner_bank_id = False

    def action_create_payments(self):
        prepaid=self.prepaid_id
        amount_adv_currency = self.currency_id._convert(
                    self.amount,
                    prepaid.currency_id,
                    self.company_id,
                    self.payment_date,
                )
        payment_vals = {
            'date': self.payment_date,
            'amount': self.amount,
            'payment_type': self.advance_type,
            'memo': self.communication,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'partner_id': prepaid.partner_id.id,
            'partner_bank_id': self.partner_bank_id.id,
            'payment_method_line_id': self.payment_method_line_id.id,
            'prepaid_id': prepaid.id,
            'amount_adv_currency': amount_adv_currency,
            'state': 'draft'
        }
        payment = self.env['account.payment'].create(payment_vals)
        prepaid.payment_id = payment.id
        payment.action_post()
        prepaid._compute_payment_amount()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'self'
        }



