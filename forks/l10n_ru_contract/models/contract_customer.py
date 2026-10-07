from odoo import api, fields, models


class ContractProfile(models.Model):
    """Вид договора: журнал, счета и условия, по которым проверяются счета и заказы.

    Эти поля читают account_move.py и invoice_saleorder.py.
    """
    _inherit = 'contract.profile'

    payable_account_id = fields.Many2one('account.account', string='Счет кредиторской задолженности')
    receivable_account_id = fields.Many2one('account.account', string='Счет дебиторской задолженности')
    max_receivable_id = fields.Float(string='Максимальная деб. задолженность')
    payment_term_id = fields.Many2one('account.payment.term', string='Условие оплаты')
    journal_id = fields.Many2one('account.journal', string='Журнал')


class PartnerContractCustomer(models.Model):
    """Коммерческие поля договора из старого монолитного contract_customer.py.

    Сам монолит (повторное объявление partner.contract.customer, contract.line,
    contract.profile, contract.day) заменён разбиением на partner_contract_customer.py
    и соседние файлы; здесь оставлено только то, чего в разбиении нет и от чего
    зависят заказ и счёт. Не перенесено: channel_id, team_id (нет моделей
    saleorder.channel и crm.team), печать docx/md, смена статуса, подсказки по заказу.
    """
    _inherit = 'partner.contract.customer'

    sec_partner_id = fields.Many2one('res.partner', string='Контрагент как в заказе')
    saleorder_id = fields.Many2one('sale.order', string='Заказ/Сделка')
    payment_term_id = fields.Many2one('account.payment.term', string='Условие оплаты')
    credit_limit = fields.Float(string='Лимит кредита')
    guid_1s = fields.Char('Код договора из 1С')
    buh_code = fields.Char('Код договора из бухгалтерии')
    manager_id = fields.Many2one('res.users', string='Менеджер по продажам')
    accountant_id = fields.Many2one('res.users', string='Бухгалтер по взаиморасчетам')
    name_dirprint = fields.Char(string='Имя нашего директора для печати')
    name_dirprint1 = fields.Char(string='Имя нашего директора для печати И.П.',
                                 compute='_compute_name_dirprint1')
    name_print1 = fields.Char(string='Имя для печати, И.П.', compute='_compute_name_print1')
    time_to_delivery_from = fields.Datetime('Время доставки от')
    time_to_delivery_to = fields.Datetime('Время доставки до')
    day_of_delivery = fields.Float('Дни доставки')
    day_of_otgruzki = fields.Float('Дни отгрузки')
    order_days_ids = fields.Many2many('contract.day', 'orderdays', 'contract_id', 'day_id', string='Дни доставки')
    shipment_days_ids = fields.Many2many('contract.day', 'shipmentdays', 'contract_id', 'day_id', string='Дни отгрузки')

    def _compute_name_dirprint1(self):
        for s in self:
            s.name_dirprint1 = s.company_id.chief_id.partner_id.name if 'chief_id' in s.company_id._fields                 and s.company_id.chief_id else False

    def _compute_name_print1(self):
        for s in self:
            director = self.env['res.partner'].search(
                [('parent_id', '=', s.partner_id.id), ('type', '=', 'director')], limit=1)
            s.name_print1 = director.name if director else False

    @api.onchange('sec_partner_id')
    def _onchange_sec_partner_id(self):
        for s in self:
            if s.sec_partner_id:
                s.partner_id = s.sec_partner_id.parent_id or s.sec_partner_id

    @api.onchange('profile_id')
    def _onchange_profile_id_payment_term(self):
        for s in self:
            if s.profile_id.payment_term_id:
                s.payment_term_id = s.profile_id.payment_term_id

    def _get_osnovanie(self):
        """Текст для поля «Основание» счёта и заказа."""
        self.ensure_one()
        if not self.date_start:
            return 'Договор № %s' % (self.name or '')
        return 'Договор № %s от %s' % (self.name or '', self.date_start.strftime('%d.%m.%Y'))
