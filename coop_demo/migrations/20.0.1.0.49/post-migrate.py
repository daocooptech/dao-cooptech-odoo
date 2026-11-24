# -*- coding: utf-8 -*-
"""Права водителя — по его умениям (№ 483): пересчитать значения."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_483_work


def migrate(cr, version):
    for table in ('coop_vacancy', 'coop_skill_offer'):
        cr.execute("""
            UPDATE %s SET attrs = NULL WHERE coop_specialization_id IN (
                SELECT id FROM coop_specialization WHERE name = 'Водитель')
        """ % table)
    # График, названный в тексте словами «сменами», «смены 2/2».
    cr.execute("""
        UPDATE coop_vacancy SET work_schedule = NULL, work_hours = NULL
         WHERE description ~* '(сменами|смены [0-9]|смены в )'
    """)
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    env.invalidate_all()
    load_483_work.load_483_work(env)
