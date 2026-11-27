# -*- coding: utf-8 -*-
"""Организации без правовой формы — форма по названию и их документы
(решение 704: все данные — на страницах организаций)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_public_docs


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for org in load_public_docs.forms_by_prefix(env):
        if org.coop_is_cooperative:
            load_public_docs.put_docs(org, ('charter', 'fees', 'profit', 'report'))
    load_public_docs.load_charters(env)
