# -*- coding: utf-8 -*-
"""Владелец у счетов, перенесённых из способов оплаты (задача 400).

Миграция 20.0.1.1.0 вставляла счета запросом и не заполняла `partner_id`
(хранимое связанное поле): правило доступа «только свои» таких счетов не
видело, и в кошельке они показывались пустыми строками. Идемпотентно.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE coop_wallet_account a
           SET partner_id = w.partner_id
          FROM coop_wallet w
         WHERE a.wallet_id = w.id AND a.partner_id IS NULL
    """)
    _logger.info('Владелец у счетов кошелька: исправлено %s', cr.rowcount)
