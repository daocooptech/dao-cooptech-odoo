from odoo import api, fields, models, exceptions, _


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    mt_contract_id = fields.Many2one('partner.contract.customer', string=_('Номер договора'))
    sec_partner_id = fields.Many2one('res.partner', string=_('Контрагент'), store=True, compute='_compute_get_pid')

    @api.depends('partner_id')
    def _compute_get_pid(self):
        for s in self:
            s.sec_partner_id = s.partner_id.parent_id if s.partner_id.parent_id else s.partner_id
