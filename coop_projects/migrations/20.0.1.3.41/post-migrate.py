# -*- coding: utf-8 -*-
"""Личные To-Do со сроком — задачи, остальные остаются заметками (№ 353)."""


def migrate(cr, version):
    cr.execute("""
        UPDATE project_task SET coop_kind = 'task'
         WHERE project_id IS NULL AND parent_id IS NULL
           AND date_deadline IS NOT NULL
    """)
