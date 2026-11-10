# -*- coding: utf-8 -*-
"""Счета участника из прежних способов оплаты (задача 400).

Раньше у кошелька были «Способы оплаты» (карта, СБП, расчётный счёт) — только
рубли и только Россия. Теперь это счета: страна, банк, вид, валюта. Каждый
прежний способ становится счётом в валюте кошелька со страной «Россия»;
способ не удаляется — окно операций пока работает с ним. Идемпотентно:
повторный прогон счёт с той же подписью не дублирует.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("SELECT id FROM res_country WHERE code = 'RU'")
    row = cr.fetchone()
    country = row[0] if row else None
    cr.execute("""
        INSERT INTO coop_wallet_account
               (wallet_id, country_id, kind, currency_id, label, is_main,
                sequence, active, create_date, write_date)
        SELECT m.wallet_id, %s,
               CASE m.kind WHEN 'card' THEN 'card' ELSE 'bank' END,
               w.currency_id, m.label, COALESCE(m.is_default, false),
               COALESCE(m.sequence, 10), true, now(), now()
          FROM coop_wallet_method m
          JOIN coop_wallet w ON w.id = m.wallet_id
         WHERE w.currency_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM coop_wallet_account a
                            WHERE a.wallet_id = m.wallet_id AND a.label = m.label)
    """, (country,))
    _logger.info('Счета кошелька из способов оплаты: добавлено %s', cr.rowcount)
