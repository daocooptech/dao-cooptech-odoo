# -*- coding: utf-8 -*-
"""Решение 704: система налогообложения у каждой организации; устав,
положения и отчётность — файлами в «Документах» вместо ссылок."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_public_docs, load_vat


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    load_vat.load_tax_systems(env)
    load_public_docs.from_old_links(env)
    # Раскладчик по папкам успел положить их в чужие полки — вынуть.
    cr.execute("UPDATE coop_document SET folder_id = NULL WHERE is_public")
