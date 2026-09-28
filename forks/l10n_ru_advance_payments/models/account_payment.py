from odoo import models, fields, api


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    prepaid_id = fields.Many2one(comodel_name='order.prepaid', string='Авансовый счет')
    amount_adv_currency = fields.Float(string='Сумма от счета', default=0)


    @api.depends('journal_id', 'partner_id', 'partner_type')
    def _compute_destination_account_id(self):
        for pay in self:
            pay.destination_account_id = False
            company = pay.company_id

            if pay.prepaid_id:
                if pay.payment_type == 'inbound' and company.advance_in_id:
                    pay.destination_account_id = company.advance_in_id.id
                elif pay.payment_type == 'outbound' and company.advance_out_id:
                    pay.destination_account_id = company.advance_out_id.id

            if pay.destination_account_id:
                continue

            partner = pay.partner_id
            # if pay.default_is_internal_transfer:
            #     pay.destination_account_id = pay.destination_journal_id.company_id.transfer_account_id
            if pay.partner_type == 'customer':
                pay.destination_account_id = self._get_partner_account(
                    partner,
                    company,
                    account_type='asset_receivable',
                    partner_account_field='property_account_receivable_id'
                )
            elif pay.partner_type == 'supplier':
                pay.destination_account_id = self._get_partner_account(
                    partner,
                    company,
                    account_type='liability_payable',
                    partner_account_field='property_account_payable_id'
                )

    def _get_partner_account(self, partner, company, account_type, partner_account_field):
        if partner:
            account = getattr(partner.with_company(company), partner_account_field, False)
            if account:
                return account.id
        account = self.env['account.account'].search([
            *self.env['account.account']._check_company_domain(company),
            ('account_type', '=', account_type),
            # Odoo 19: поля `deprecated` у счёта нет — его заменил `active`,
            # и архивные счета поиск и так не возвращает. Форк ДАО КООПТЕХ.
        ], limit=1)

        return account.id if account else False