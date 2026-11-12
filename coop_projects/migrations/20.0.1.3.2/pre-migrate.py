# -*- coding: utf-8 -*-
"""Потребности переехали из вкладки на страницу проекта (12.11.2026).

Кнопка «Разобрать заявки» цеплялась за `//page[@name='needs']`. При
обновлении родитель меняется раньше, чем перечитывается кнопка, и
проверка вида падает на старом пути. Путь кнопки правим до загрузки
файлов на такой, что верен и для старого родителя, и для нового.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_ui_view
           SET arch_db = replace(arch_db::text,
                   '//page[@name=''needs'']/field[@name=''need_ids'']',
                   '//field[@name=''need_ids'']')::jsonb
         WHERE id = (SELECT res_id FROM ir_model_data
                      WHERE module = 'coop_projects'
                        AND name = 'view_coop_project_form_offers_button')
    """)
