# -*- coding: utf-8 -*-
"""Телефон и почта у всех организаций — «показывать» (решение 410, п. 12).

До этого переключатели на странице организации не действовали, и телефон
был виден всем; теперь они привязаны, и без этой правки телефон и почта
разом пропали бы у всех организаций платформы."""


def migrate(cr, version):
    cr.execute("""
        UPDATE res_partner
           SET coop_show_phone = TRUE, coop_show_email = TRUE
         WHERE is_company
           AND (coop_show_phone IS NOT TRUE OR coop_show_email IS NOT TRUE)
    """)
