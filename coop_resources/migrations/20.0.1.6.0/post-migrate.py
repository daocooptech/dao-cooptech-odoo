# -*- coding: utf-8 -*-
"""Единицы измерения — справочником (решение 634).

Раньше единица была свободным текстом: «шт.», «кг», «рулон», «ходка».
Справочник заводим из того, что люди уже написали: каждое слово становится
одобренной единицей, иначе в форме у старых объявлений единица пропала бы
из списка. Хранимое значение остаётся текстом — ничего не переписываем.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        INSERT INTO coop_resource_uom (name, sequence, state, create_date, write_date)
        SELECT DISTINCT ON (lower(label)) label, 200, 'approved', now(), now()
          FROM (
            SELECT btrim(price_unit_label) AS label FROM coop_resource_term
            UNION ALL
            SELECT btrim(price_unit_label) FROM coop_resource
            UNION ALL
            SELECT btrim(uom_label) FROM coop_resource
          ) used
         WHERE label IS NOT NULL AND label <> '' AND length(label) <= 40
           AND NOT EXISTS (SELECT 1 FROM coop_resource_uom u
                            WHERE lower(u.name) = lower(used.label))
         ORDER BY lower(label), label
    """)
    _logger.info('Единицы измерения: из прежних записей добавлено %s', cr.rowcount)
    # Новые поля считаются при обновлении, но `has_wholesale` у уже
    # заполненных условий нужно пересчитать явно.
    cr.execute("""
        UPDATE coop_resource r
           SET has_wholesale = true
         WHERE EXISTS (SELECT 1 FROM coop_resource_term t
                        WHERE t.resource_id = r.id AND t.code = 'sale'
                          AND t.bulk_qty > 0 AND t.bulk_price > 0)
    """)
