# -*- coding: utf-8 -*-
"""Коды выдачи для заказов, заведённых до того, как коды появились.

Без этого у старых заказов код пуст, и на раздаче участник называет
пустоту. Новые заказы получают код при создании — этот проход нужен
ровно один раз, для тех, что были раньше.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT id FROM coop_groupbuy_order
         WHERE pickup_code IS NULL OR pickup_code = ''
    """)
    ids = [row[0] for row in cr.fetchall()]
    if not ids:
        return

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Order = env['coop.groupbuy.order']
    for order in Order.browse(ids):
        order.pickup_code = Order._new_pickup_code()
    _logger.info('Коды выдачи проставлены: %s заказов', len(ids))
