# -*- coding: utf-8 -*-
"""Остаток к сведению у существующих объявлений — весь объём (решение 417)."""


def migrate(cr, version):
    cr.execute("""
        UPDATE coop_crypto_offer
           SET quantity_left = amount_max
         WHERE quantity_left IS NULL OR quantity_left = 0
    """)
    cr.execute("""
        UPDATE coop_crypto_offer o SET order_type = 'limit' WHERE order_type IS NULL
    """)
