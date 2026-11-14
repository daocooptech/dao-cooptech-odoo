# -*- coding: utf-8 -*-
"""Курсам доллара — снова доллар.

`coop_l10n_ru._coop_platform_rub` при каждом обновлении переписывал во всех
таблицах `coop_*` доллар в рубль, курсы ЦБ тоже: на боевой 14.11.2026 было
четыре «рублёвых» курса по ~82 ₽ за 10–14.11 — это курсы доллара. Курса у
рубля не бывает (`coop_rate` отдаёт для него 1), поэтому любая строка курса
рубля — испорченный доллар: где доллар на ту же дату уже есть, она лишняя.
Идемпотентно.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("SELECT id, name FROM res_currency WHERE name IN ('RUB', 'USD')")
    ids = {name: cid for cid, name in cr.fetchall()}
    if len(ids) < 2:
        return
    rub, usd = ids['RUB'], ids['USD']
    cr.execute("""
        DELETE FROM coop_currency_rate r
         WHERE r.currency_id = %s
           AND EXISTS (SELECT 1 FROM coop_currency_rate u
                        WHERE u.currency_id = %s AND u.date = r.date)
    """, (rub, usd))
    dropped = cr.rowcount
    cr.execute("UPDATE coop_currency_rate SET currency_id = %s WHERE currency_id = %s",
               (usd, rub))
    _logger.info('Курсы доллара из рублёвых: возвращено %s, лишних удалено %s',
                 cr.rowcount, dropped)
