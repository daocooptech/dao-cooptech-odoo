# -*- coding: utf-8 -*-
"""Специализация и режим НДС — у всех организаций, кроме самой платформы
(владелец 27.11); система налогообложения — согласованно с новым режимом."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_org_profiles, load_vat


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    load_org_profiles.fill_specializations(env)
    if 'coop.vat.regime' in env:
        load_vat.align_tax_systems(load_vat.load_vat_regimes(env))
        load_vat.load_companies(env)
