# -*- coding: utf-8 -*-
"""Город объявления — из города владельца, где он пуст (11.11.2026:
«чёрная полоска с городом не у всех» — 127 опубликованных без города,
у всех владельцев город есть). Идемпотентно."""


def migrate(cr, version):
    cr.execute("""
        UPDATE coop_resource r SET city = o.city
          FROM res_partner o
         WHERE o.id = r.owner_id AND COALESCE(r.city, '') = ''
           AND COALESCE(o.city, '') <> ''""")
