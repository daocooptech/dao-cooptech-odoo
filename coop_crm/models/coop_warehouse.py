# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoopWarehouse(models.Model):
    _inherit = 'coop.warehouse'

    # Склад на платформе и склад в учёте организации — одно место
    # (владелец 27.10.2026). Поле — только тем, кому открыт «Склад» или
    # «Производство»: остальным склад учёта чужой компании не читается.
    stock_warehouse_id = fields.Many2one(
        'stock.warehouse', string='Склад в учёте', copy=False, index=True,
        groups='stock.group_stock_user',
        help='Склад компании учёта организации: остатки, перемещения и '
             'выпуски партий идут на него.')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.owner_id._coop_ensure_warehouse()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'owner_id' in vals:
            self.owner_id._coop_ensure_warehouse()
        return result

    def action_open_stock_warehouse(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'stock.warehouse',
            'res_id': self.stock_warehouse_id.id, 'view_mode': 'form',
            'views': [(False, 'form')], 'target': 'current',
            'context': {'coop_catalog': False, 'coop_section': False},
        }


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    coop_warehouse_ids = fields.One2many(
        'coop.warehouse', 'stock_warehouse_id', string='На платформе',
        help='Карточка этого склада в разделе «Склады» платформы.')
