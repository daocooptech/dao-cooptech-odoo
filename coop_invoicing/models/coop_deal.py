from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Способы, у которых есть продавец и деньги. У дара, обмена, взаимного
# кредита и доли в проекте счёта нет: там никто никому не платит за
# отгрузку, и УПД на них был бы документом о том, чего не было.
INVOICED_WAYS = ('sale', 'purchase', 'batch', 'rent', 'service', 'job')
INVOICED_STATES = ('active', 'acceptance', 'done')


class CoopDeal(models.Model):
    _inherit = 'coop.deal'

    coop_invoice_ids = fields.One2many(
        'account.move', 'coop_deal_id', string='Счета', readonly=True)
    coop_invoice_count = fields.Integer(compute='_compute_coop_invoice_count')
    coop_seller_id = fields.Many2one(
        'res.partner', string='Продавец', compute='_compute_coop_seller')
    coop_can_invoice = fields.Boolean(compute='_compute_coop_can_invoice')

    @api.depends('coop_invoice_ids')
    def _compute_coop_invoice_count(self):
        for deal in self:
            deal.coop_invoice_count = len(deal.sudo().coop_invoice_ids)

    @api.depends('party_a_id', 'party_b_id', 'role_a', 'role_b', 'way')
    def _compute_coop_seller(self):
        for deal in self:
            deal.coop_seller_id = deal._coop_payer_payee()[1] if deal.party_a_id and deal.party_b_id else False

    @api.depends_context('uid')
    @api.depends('state', 'way', 'amount', 'coop_invoice_ids.state', 'party_a_id', 'party_b_id')
    def _compute_coop_can_invoice(self):
        treasury = self.env.user.coop_treasury_partner_ids
        for deal in self:
            seller = deal.coop_seller_id
            deal.coop_can_invoice = bool(
                deal.state in INVOICED_STATES
                and deal.way in INVOICED_WAYS
                and deal.amount > 0
                and seller.is_company
                and seller in treasury
                and not deal.sudo().coop_invoice_ids.filtered(
                    lambda m: m.move_type == 'out_invoice' and m.state != 'cancel')
            )

    def _coop_shipped_on(self):
        """Дата отгрузки для УПД: подписание акта, а пока его нет — сегодня."""
        self.ensure_one()
        return self.act_confirmed_on or fields.Date.context_today(self)

    def _coop_invoice_vals(self, date=None):
        """Значения счёта по сделке в компании продавца."""
        self.ensure_one()
        seller, buyer = self.coop_seller_id, self._coop_payer_payee()[0]
        date = date or self._coop_shipped_on()
        tax = seller._coop_sale_tax_at(date)
        company = seller.coop_company_id
        lines = [(0, 0, {
            'name': line.name,
            'quantity': line.quantity or 1.0,
            'price_unit': line.price_unit,
            'tax_ids': [(6, 0, tax.ids)],
        }) for line in self.line_ids if line.price_unit]
        if not lines:
            # Сделка без спецификации — одной строкой на всю сумму.
            lines = [(0, 0, {
                'name': self.name,
                'quantity': 1.0,
                'price_unit': self.amount,
                'tax_ids': [(6, 0, tax.ids)],
            })]
        return {
            'move_type': 'out_invoice',
            'company_id': company.id,
            'partner_id': buyer.id,
            'invoice_date': date,
            'invoice_origin': self.number,
            'ref': self.name,
            'coop_deal_id': self.id,
            'invoice_line_ids': lines,
        }

    def action_coop_create_invoice(self):
        """Выставить счёт по сделке от имени продавца.

        Под sudo после проверки полномочия: счёт заводится в компании
        продавца, а она у человека может быть ещё не включена в списке
        активных.
        """
        self.ensure_one()
        seller = self.coop_seller_id
        if not self.coop_can_invoice:
            if seller not in self.env.user.coop_treasury_partner_ids:
                raise UserError(_(
                    'Выставить счёт от имени «%s» может только тот, у кого '
                    'есть полномочие «Бухгалтерия и счета».') % seller.display_name)
            raise UserError(_('По этой сделке счёт выставить нельзя или он уже выставлен.'))
        company = seller._coop_ensure_company()
        move = self.env['account.move'].sudo().with_company(company).create(
            self._coop_invoice_vals())
        return move._coop_form_action()

    def action_coop_open_invoices(self):
        self.ensure_one()
        moves = self.sudo().coop_invoice_ids
        if len(moves) == 1:
            return moves._coop_form_action()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Счета по сделке %s') % self.number,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }
