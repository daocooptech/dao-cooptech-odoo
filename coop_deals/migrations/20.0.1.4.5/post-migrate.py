# -*- coding: utf-8 -*-
"""Отзывы: дата раскрытия, одиночные — через 14 дней (решения 490, 491).

Сделкам с двумя отзывами — дата раскрытия по второму отзыву. Одиночным,
у которых с закрытия прошло 14 дней, — день закрытия плюс 14, без
извещений: суточное задание извещает только о новых. Затем признак
раскрытия, итог сделки и доверие — заново: в доверие теперь идут только
раскрытые отзывы.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE coop_deal d
           SET reviews_opened_on = r.last::date
          FROM (SELECT deal_id, max(create_date) AS last,
                       count(DISTINCT side) AS sides
                  FROM coop_deal_review GROUP BY deal_id) r
         WHERE r.deal_id = d.id AND r.sides >= 2
           AND d.reviews_opened_on IS NULL
    """)
    both = cr.rowcount
    cr.execute("""
        UPDATE coop_deal d
           SET reviews_opened_on = d.closed_on + 14
         WHERE d.state = 'done' AND d.reviews_opened_on IS NULL
           AND d.closed_on + 14 <= current_date
           AND EXISTS (SELECT 1 FROM coop_deal_review r WHERE r.deal_id = d.id)
    """)
    single = cr.rowcount
    env = api.Environment(cr, SUPERUSER_ID, {})
    deals = env['coop.deal'].search([('review_ids', '!=', False)])
    deals._compute_reviews_visible()
    deals._compute_outcome()
    deals.flush_recordset(['reviews_visible', 'outcome'])
    deals.review_ids.flush_recordset()
    cr.execute("""
        UPDATE coop_deal_review r SET visible = d.reviews_visible
          FROM coop_deal d WHERE d.id = r.deal_id
           AND r.visible IS DISTINCT FROM d.reviews_visible
    """)
    env.invalidate_all()
    env['res.partner']._coop_recompute_all_deal_stats()
    _logger.info('coop_deals 20.0.1.4.5: раскрыто по двум отзывам %s, '
                 'одиночных через 14 дней %s', both, single)
