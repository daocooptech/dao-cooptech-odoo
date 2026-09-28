from odoo import models, fields, api


class OrderPrepaidLine(models.Model):
    _name = 'order.prepaid.line'
    _inherit = "analytic.mixin"
    _description = 'Order Prepaid line'


    product_id = fields.Many2one(comodel_name='product.product', string='Продукт')
    name = fields.Char(string='Метка', compute='_compute_name')
    label = fields.Char(string='Метка')
    account_id = fields.Many2one(comodel_name='account.account', string='Счёт')
    quantity = fields.Float(string='Количество', default=1, digits='Product Unit of Measure')
    product_uom_id = fields.Many2one(comodel_name='uom.uom', string='Ед. измерения', compute='_compute_product_uom_id')
    price_unit = fields.Float(string='Цена', digits='Product Price', default=1)
    tax_ids = fields.Many2many(comodel_name='account.tax', string="Налоги")
    prepaid_id = fields.Many2one(comodel_name='order.prepaid', string='Авансовый счет')
    sale_ids = fields.Many2many(comodel_name='sale.order.line', string='Связные строки заказа')
    analytic_distribution = fields.Json(string='Аналитическое распределение')


    price_subtotal = fields.Monetary(
        string='Subtotal',
        compute='_compute_totals', store=True,
        currency_field='currency_id',
    )

    price_total = fields.Monetary(
        string='Total',
        compute='_compute_totals', store=True,
        currency_field='currency_id',
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        compute='_compute_currency_id', store=True, readonly=False, precompute=True,
        required=True,
    )

    @api.depends('prepaid_id.currency_id')
    def _compute_currency_id(self):
        for line in self:
            line.currency_id = line.prepaid_id.currency_id


    @api.depends('quantity', 'price_unit', 'tax_ids', 'currency_id')
    def _compute_totals(self):
        for line in self:
            subtotal = line.quantity * line.price_unit
            if line.tax_ids:
                taxes_res = line.tax_ids.compute_all(
                    line.price_unit,
                    quantity=line.quantity,
                    currency=line.currency_id,
                    product=line.product_id,
                    partner=self.prepaid_id.partner_id,
                    is_refund=False,
                )
                line.price_subtotal = taxes_res['total_excluded']
                line.price_total = taxes_res['total_included']
            else:
                line.price_total = line.price_subtotal = subtotal


    @api.depends('product_id')
    def _compute_product_uom_id(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id
            else:
                line.product_uom_id = False


    @api.depends('product_id')
    def _compute_name(self):
        for line in self:
            if line.product_id:
                line.name = line.product_id.name
            else:
                line.name = ''
