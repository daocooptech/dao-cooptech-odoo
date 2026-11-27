# -*- coding: utf-8 -*-
"""Дашборды организаций (решение 707), правки данных:
- у счетов из заказов продавцом стоял OdooBot (заказы заводит суперпользователь) —
  ставим продавца заказа;
- отгрузки витрины списались с корня склада и ушли в минус — минусовые
  остатки витрины выравниваем инвентаризацией."""
import random

from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_sales as ls


def migrate(cr, version):
    cr.execute("""
        UPDATE account_move m SET invoice_user_id = x.user_id
          FROM (SELECT DISTINCT ON (aml.move_id) aml.move_id, so.user_id
                  FROM sale_order_line_invoice_rel r
                  JOIN sale_order_line sol ON sol.id = r.order_line_id
                  JOIN sale_order so ON so.id = sol.order_id
                  JOIN account_move_line aml ON aml.id = r.invoice_line_id
                 WHERE so.user_id IS NOT NULL) x
         WHERE m.id = x.move_id AND (m.invoice_user_id IS NULL OR m.invoice_user_id = %s)
    """, (SUPERUSER_ID,))
    env = api.Environment(cr, SUPERUSER_ID, {})
    rnd = random.Random(20261127)
    for org in ls._showcase(env, 'dashkevich'):
        company = org.coop_company_id
        quants = env['stock.quant'].sudo().search([
            ('company_id', '=', company.id), ('quantity', '<', 0),
            ('location_id.usage', '=', 'internal')])
        for quant in quants:
            quant.with_company(company).with_context(inventory_mode=True).write(
                {'inventory_quantity': rnd.choice((10, 20, 30, 50))})
            quant.with_company(company).with_context(inventory_mode=True).action_apply_inventory()
