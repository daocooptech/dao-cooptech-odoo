# -*- coding: utf-8 -*-
"""Отклики навыками и услугами на трудовые потребности (№ 474)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_474_skills


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {
        'tracking_disable': True, 'mail_create_nolog': True, 'mail_notrack': True})
    load_474_skills.load_474_skills(env)
