# -*- coding: utf-8 -*-
"""«от / до / ровно / по договорённости» — во вкладку способа.

Владелец 27.10.2026: «убрать Цена на карточке, цена настраивается в
каждой вкладке». Уточнение цены переехало с объявления на строку
условий; у заведённых раньше строк его берём с самого объявления, иначе
все стали бы «ровно».
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE coop_resource_term t
           SET price_kind = r.price_kind
          FROM coop_resource r
         WHERE t.resource_id = r.id
           AND r.price_kind IS NOT NULL
    """)
