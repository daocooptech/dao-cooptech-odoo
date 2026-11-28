# -*- coding: utf-8 -*-
"""Витрина dashkevich для «Аналитики» (задача 494, поправки владельца 28.11):
пайщики СПК «Степь» и dashkevich в её правлении; лиды ТСН «Прибрежное»."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_showcase_crm, load_showcase_shares


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    load_showcase_shares.load_showcase_shares(env)
    load_showcase_crm.load_showcase_crm(env)
