from odoo import api, fields, models, exceptions, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    mt_contract_id = fields.Many2one('partner.contract.customer', string=_('Номер договора'))
    sf_number = fields.Char(string=_('Номер с/ф'))
    osnovanie = fields.Char(string=_('Основание'))
    sec_partner_id = fields.Many2one('res.partner', string=_('Контрагент'), store=True, compute='_compute_get_pid')
    stamp = fields.Boolean(string=_('Печать и подпись'), related='mt_contract_id.stamp')

    @api.depends('partner_id')
    def _compute_get_pid(self):
        for s in self:
            s.sec_partner_id = s.partner_id.parent_id if s.partner_id.parent_id else s.partner_id

    @api.onchange('mt_contract_id')
    def set_ons(self):
        if self.mt_contract_id:
            self.osnovanie = 'Договор № ' + self.mt_contract_id.name + ' от ' + fields.Datetime.from_string(
                self.mt_contract_id.date_start).strftime("%d.%m.%Y")

    @api.constrains('state')
    def invoice_fields_check(self):
        for s in self:
            if s.state == 'posted':
                if s.mt_contract_id:
                    errors_list = []
                    journal_in_contract = s.mt_contract_id.profile_id.journal_id
                    payment_term_in_contract = s.mt_contract_id.profile_id.payment_term_id
                    receivable_in_contract = s.mt_contract_id.profile_id.receivable_account_id

                    if journal_in_contract != s.journal_id:
                        errors_list.append(f'Отличается Журнал - [{s.journal_id.name}] '
                                           f'и указанный в договоре №{s.mt_contract_id.name} '
                                           f'Журнал - [{journal_in_contract.name}]\n\n')

                    if payment_term_in_contract != s.invoice_payment_term_id:
                        errors_list.append(f'Отличается поле "Условие оплаты" в инвойсе '
                                           f'[Условие оплаты - {s.invoice_payment_term_id.name}] '
                                           f'и указанный в договоре №{s.mt_contract_id.name} '
                                           f'[Условие оплаты - {payment_term_in_contract.name}]\n\n')

                    if receivable_in_contract not in s.line_ids.account_id:
                        errors_list.append(f'Отличается поле "Счет дебиторской задолженности" в инвойсе '
                                           f'и указанный в договоре №{s.mt_contract_id.name}')

                    if errors_list:
                        raise exceptions.ValidationError(''.join(errors_list))