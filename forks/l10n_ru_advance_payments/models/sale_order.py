from odoo import models, fields
from odoo.fields import Command


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    prepaid_advance_count = fields.Integer(string='Закупки', compute='_compute_prepaid_advance_count')

    def _compute_prepaid_advance_count(self):
        for el in self:
            prepaid = self.env['order.prepaid'].search([('sale_order_id', '=', self.id), ('state', '!=', 'cancel')])
            el.prepaid_advance_count = len(prepaid)


    def action_prepaid_advance(self):
        action = self.env['ir.actions.act_window']._for_xml_id('l10n_ru_advance_payments.action_order_prepaid')
        prepaid = self.env['order.prepaid'].search([('sale_order_id', '=', self.id), ('state', '!=', 'cancel')])
        if len(prepaid) > 1:
            action['domain'] = [('sale_order_id', '=', self.id)]
            action['context'] = {
                'group_by': ['advance_type']
            }
        elif len(prepaid) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'order.prepaid',
                'res_id': prepaid.id,
                'view_mode': 'form',
                'view_type': 'form',
                'target': 'self'
            }
        return action


    def button_advance(self):
        prepaid_vals = {
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'sale_order_id': self.id,
            'prepaid_line': [],
        }
        for line in self.order_line:
            elem = self._prepare_line(line)
            prepaid_vals['prepaid_line'].append((0, 0, elem))
        prepaid = self.env['order.prepaid'].create(prepaid_vals)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'order.prepaid',
            'res_id': prepaid.id,
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'self'
        }

    def _prepare_line(self, line):
        res = {
            'product_id': line.product_id.id,
            'product_uom_id': line.product_uom_id.id,
            'quantity': line.product_uom_qty,
            'price_unit': line.price_unit,
            'tax_ids': [(6, 0, line.tax_ids.ids)],
            'sale_ids': [Command.link(line.id)],
        }
        if line.analytic_distribution:
            res['analytic_distribution'] = line.analytic_distribution
        return res

