from datetime import date

from odoo import api, fields, models, exceptions


class SaleOrder(models.Model):
    """Договор в заказе: из него в счёт (в том числе на аванс) переходят договор и основание."""
    _inherit = 'sale.order'

    mt_contract_id = fields.Many2one('partner.contract.customer', string='Номер договора')
    sec_partner_id = fields.Many2one('res.partner', string='Контрагент', store=True, compute='_compute_sec_partner_id')
    stamp = fields.Boolean(string='Печать и подпись', related='mt_contract_id.stamp')

    @api.depends('partner_id')
    def _compute_sec_partner_id(self):
        for s in self:
            s.sec_partner_id = s.partner_id.parent_id if s.partner_id.parent_id else s.partner_id

    @api.onchange('mt_contract_id')
    def _onchange_mt_contract_id(self):
        for s in self:
            if s.mt_contract_id.payment_term_id:
                s.payment_term_id = s.mt_contract_id.payment_term_id

    @api.constrains('state')
    def _check_late_payment(self):
        for s in self:
            if s.mt_contract_id and s.state == 'sale':
                max_receivable = s.mt_contract_id.profile_id.max_receivable_id  # предел дебиторской задолженности
                if not max_receivable:
                    continue
                # просроченные счета контрагента из заказа
                invoices = self.env['account.move'].search([
                    ('partner_id', '=', s.partner_id.id),
                    ('state', '=', 'posted'),
                    ('payment_state', 'not in', ['paid', 'reversed']),
                    ('move_type', '=', 'out_invoice'),
                    ('invoice_date_due', '<', date.today())])
                late_amount = sum(invoices.mapped('amount_residual'))
                if late_amount > max_receivable:
                    nl = chr(10)
                    message = (
                        'Нельзя подтвердить заказ, так как у контрагента %(partner)s нарушено '
                        'условие по дебиторской задолженности.' + nl * 2 +
                        'Контрагент %(partner)s должен %(late)s руб.' + nl +
                        'Максимальная дебиторская задолженность, указанная в '
                        'договоре № %(contract)s - %(limit)s руб.' + nl * 2 +
                        'Проверьте следующие неоплаченные счета контрагента:' + nl + '%(invoices)s')
                    raise exceptions.ValidationError(message % {
                        'partner': s.sec_partner_id.name,
                        'late': late_amount,
                        'contract': s.mt_contract_id.name,
                        'limit': max_receivable,
                        'invoices': ', '.join(invoices.mapped('name')),
                    })

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        if self.mt_contract_id:
            invoice_vals['mt_contract_id'] = self.mt_contract_id.id
            invoice_vals['osnovanie'] = self.mt_contract_id._get_osnovanie()
        return invoice_vals

