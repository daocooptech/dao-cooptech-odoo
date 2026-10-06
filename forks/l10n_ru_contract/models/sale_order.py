from odoo import api, fields, models, exceptions, _
from datetime import datetime


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    mt_contract_id = fields.Many2one('partner.contract.customer', string='Номер договора')
    sec_partner_id = fields.Many2one('res.partner', string='Контрагент', store=True, compute='_compute_get_pid')
    stamp = fields.Boolean(string='Печать и подпись', related='mt_contract_id.stamp')

    @api.depends('partner_id')
    def _compute_get_pid(self):
        for s in self:
            s.sec_partner_id = s.partner_id.parent_id if s.partner_id.parent_id else s.partner_id

    @api.onchange('mt_contract_id')
    def set_ons(self):
        if self.mt_contract_id:
            self.payment_term_id = self.mt_contract_id.payment_term_id

    @api.constrains('state')
    def late_payment_check(self):
        if self.mt_contract_id:
            if self.state == 'sale':
                late_invoices_count = 0
                max_receivable = self.mt_contract_id.profile_id.max_receivable_id  # макс. деб. задолженность в договоре
                # ищу просроченные инвойсы контрагента указанного в заказе со стейтом "Подтверждено"
                invoices_obj = self.env['account.move'].search([('partner_id', '=', self.partner_id.id),
                                                                ('state', '=', 'posted'),
                                                                ('invoice_date_due', '<', datetime.now().date())])

                for invoice in invoices_obj:
                    late_invoices_count += invoice.amount_residual  # складываю деб. задолженность по просроченным инвойсам

                if late_invoices_count > max_receivable:
                    raise exceptions.ValidationError(
                        f'Нельзя подтвердить заказ, так как у контрагента {self.sec_partner_id.name} нарушено '
                        f'условие по дебиторской задолженности.\n\n'
                        f'Контрагент {self.sec_partner_id.name} должен {late_invoices_count}руб.\n'
                        f'Максимальная дебиторская задолженность указанная в '
                        f'договоре №{self.mt_contract_id.name} - {max_receivable}руб.\n\n'
                        f'Проверьте следующие неоплаченные счета контрагента:\n'
                        f'{", ".join([invoice.name for invoice in invoices_obj])}')

    # при выбора счета "Обычный счет"
    @api.model
    def _create_invoices(self, grouped=False, final=False, date=None):
        res = super(SaleOrder, self)._create_invoices(grouped, final, date)
        if self.mt_contract_id:
            res.write({'mt_contract_id': self.mt_contract_id,
                       'journal_id': self.mt_contract_id.profile_id.journal_id})
        return res