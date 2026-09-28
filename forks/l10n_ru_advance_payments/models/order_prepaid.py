from odoo import models, fields, api

class OrderPrepaid(models.Model):
    _name = 'order.prepaid'
    _description = 'Авансовые платежи'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Название', default='Draft', copy=False)
    partner_id = fields.Many2one(comodel_name='res.partner', string='Контрагент')
    invoice_partner_display_name = fields.Char(compute='_compute_invoice_partner_display_info', store=True)

    payment_terms = fields.Char(string='Условия оплаты')
    invoice_date = fields.Date(string='Дата счета', default=fields.Date.context_today, required=True)
    invoice_date_due = fields.Date(string='Срок оплаты', default=fields.Date.context_today, required=True)
    company_id = fields.Many2one(comodel_name='res.company', string='Компания')
    sale_order_id = fields.Many2one(comodel_name='sale.order', string='Заказ продаж')
    advance_type = fields.Selection(selection=[('outbound', 'Исходящий'),('inbound', 'Входящий')],
                                    string='Тип платежа', default='inbound')
    comment = fields.Text(string='Комментарий')
    state = fields.Selection(selection=[('cancel', 'Отменено'),
                                        ('draft', 'Черновик'),
                                        ('posted', 'Проведено')],
                                        string='Статус', default='draft')
    prepaid_line = fields.One2many(comodel_name='order.prepaid.line', inverse_name='prepaid_id', string='Строки счета')

    currency_id = fields.Many2one(comodel_name='res.currency', string='Валюта', tracking=True, required=True, readonly=False,
                                  compute='_compute_currency_id', inverse='_inverse_currency_id',
                                  store=True, precompute=True)
    partner_bank_id = fields.Many2one(comodel_name='res.partner.bank', string="Банковский счёт получателя")
    amount = fields.Monetary(currency_field='currency_id', store=True, readonly=False,
                             compute='_compute_amount', string='Всего')

    payment_line_ids = fields.One2many(comodel_name='account.payment', inverse_name='prepaid_id',
                                       string='Связанные платежи', compute_sudo=True, store=True)
    company_partner_id = fields.Many2one(string='Контакт компании', related='company_id.partner_id')

    payment_state = fields.Selection(selection=[('not_paid', 'Не оплачен'),
                                                ('in_payment', 'В оплате'),
                                                ('paid', 'Оплачено'),
                                                ('partial', 'Частично оплачено'),
                                                ],
                                     string="Статус платежа", readonly=True, copy=False, tracking=True,
                                     compute='_compute_payment_state', store=True)
    payment_id = fields.Many2one(comodel_name='account.payment', string='Платеж')
    payment_amount = fields.Monetary(currency_field='currency_id', compute='_compute_payment_amount', store=True, string='Выплачено')
    amount_sum_line = fields.Monetary(currency_field='currency_id', store=True, readonly=False,
                             compute='_compute_amount_sum_line', string='Сумма')

    amount_residual = fields.Monetary(currency_field='currency_id', store=True, readonly=False,
                                      compute='_compute_amount_residual', string='Остаток долга', default=0, copy=False)

    all_total = fields.Monetary(currency_field='currency_id', store=True, readonly=True,
                                      compute='_compute_all_total', string='Всего', default=0, copy=False)

    th_field_taxes = fields.Boolean(string='Проверка столбца налогов', compute='_th_field_taxes', store=True)

    @api.depends('prepaid_line.tax_ids')
    def _th_field_taxes(self):
        for rec in self:
            values = rec.prepaid_line.mapped('tax_ids')
            if values:
                rec.th_field_taxes = True
            else:
                rec.th_field_taxes = False

    @api.depends('amount')
    def _compute_all_total(self):
        for rec in self:
            if rec.amount > 0:
                rec.all_total = -(rec.amount) if rec.advance_type == 'outbound' else rec.amount
            else:
                rec.all_total = 0

    @api.depends('partner_id', 'partner_id.display_name')
    def _compute_invoice_partner_display_info(self):
        for record in self:
            vendor_display_name = record.partner_id.display_name if record.partner_id else ''
            record.invoice_partner_display_name = vendor_display_name

    @api.depends('amount', 'payment_amount', 'state')
    def _compute_amount_residual(self):
        for rec in self:
            if rec.state == 'posted':
                rec.amount_residual = rec.amount - abs(rec.payment_amount)
            else:
                rec.amount_residual = 0

    @api.depends('prepaid_line', 'prepaid_line.tax_ids')
    def _compute_amount_sum_line(self):
        for rec in self:
            amount = 0
            for el in rec.prepaid_line:
                amount += el.price_subtotal
            rec.amount_sum_line = amount


    @api.depends('payment_amount', 'payment_line_ids.reconciled_statement_line_ids')
    def _compute_payment_state(self):
        if not self.payment_line_ids:
            self.payment_state = 'not_paid'
        elif abs(self.payment_amount) != 0:
            if abs(self.payment_amount) >= self.amount:
                bool = True
                for rec in self.payment_line_ids:
                    if not rec.reconciled_statement_line_ids:
                        bool = False
                        break
                self.payment_state = 'paid' if bool else 'in_payment'
            else:
                self.payment_state = 'partial'
        else:
            self.payment_state = 'not_paid'

    @api.depends('payment_line_ids', 'payment_line_ids.state')
    def _compute_payment_amount(self):
        for rec in self:
            payments = self.env['account.payment'].with_company(rec.company_id)
            records = payments.search([('state', '=', 'posted'),
                                      ('prepaid_id', '=', rec.id),
                                      ('company_id', '=', rec.company_id.id)])
            amount = sum(records.mapped('amount_adv_currency'))
            rec.payment_amount = amount


    @api.depends('prepaid_line')
    def _compute_amount(self):
        for rec in self:
            amount = 0
            for el in rec.prepaid_line:
                amount += el.price_unit * el.quantity
            rec.amount = amount

    @api.depends('company_id')
    def _compute_currency_id(self):
        for invoice in self:
            invoice.currency_id = invoice.company_id.currency_id

    @api.onchange('currency_id')
    def _inverse_currency_id(self):
        self.currency_id = self.currency_id


    def action_post(self):
        if self.name == 'Draft':
            self.name = self.env['ir.sequence'].next_by_code('order.prepaid')
        self.state = 'posted'

    def button_draft(self):
        self.state = 'draft'
        payments = self.env['account.payment'].with_company(self.company_id)
        records = payments.search([('prepaid_id', '=', self.id), ('company_id', '=', self.company_id.id)])
        if records:
            for el in records:
                el.action_draft()
                el.action_cancel()
                el.unlink()


    def button_cancel(self):
        self.state = 'cancel'


    def action_register_payment(self):
        journals = self.env['account.journal'].with_company(self.company_id.id)
        journal = journals.search([('type', 'in', ['bank', 'cash']), ('company_id', '=', self.company_id.id)])
        if journal:
            if self.partner_bank_id:
                journal_bank = journal.search([('bank_account_id', '=', self.partner_bank_id.id)], limit=1)
                journal_id = journal_bank.id if journal_bank else journal[0].id
            else:
                journal_id = journal[0].id
        else:
            journal_id = False

        delta_amount = self.amount - abs(self.payment_amount)
        default_amount = delta_amount if delta_amount > 0 else 0

        return {
            'name': 'Регистрация платежа',
            'res_model': 'payment.register.prepaid',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'context': {
                'default_prepaid_id': self.id,
                'default_company_id': self.company_id.id,
                'default_communication': self.name,
                'default_amount': default_amount,
                'default_amount_const': default_amount,
                'default_journal_id': journal_id
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }


