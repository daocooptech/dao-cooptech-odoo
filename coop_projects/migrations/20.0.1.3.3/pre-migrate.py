# -*- coding: utf-8 -*-
"""Список потребностей со страницы проекта убран (12.11.2026).

Вид списка и кнопка «Разобрать заявки», что на нём держалась, из
файлов удалены. Движок убрал бы их только в конце обновления, а до
того проверял бы кнопку на уже пустом месте и падал. Удаляем заранее:
сначала наследника, потом родителя.
"""


def migrate(cr, version):
    for name in ('view_coop_project_form_offers_button',
                 'view_coop_project_form_needs'):
        cr.execute("""
            DELETE FROM ir_ui_view WHERE id IN (
                SELECT res_id FROM ir_model_data
                 WHERE module = 'coop_projects' AND name = %s
                   AND model = 'ir.ui.view')
        """, (name,))
        cr.execute("""
            DELETE FROM ir_model_data
             WHERE module = 'coop_projects' AND name = %s
        """, (name,))
