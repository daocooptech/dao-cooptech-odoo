# -*- coding: utf-8 -*-
"""Заметки организаций — в пространство «Организация» (№ 353)."""


def migrate(cr, version):
    cr.execute("""
        UPDATE project_task SET coop_space = 'org'
         WHERE coop_org_id IS NOT NULL AND project_id IS NULL
    """)
