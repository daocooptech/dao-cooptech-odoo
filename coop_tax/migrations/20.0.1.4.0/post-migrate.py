# -*- coding: utf-8 -*-
"""Решение 642: нерезидентам по патенту и гражданам ЕАЭС НДФЛ — по шкале
13–22 %. Выплаты, уже посчитанные по 30 %, пересчитываются; признак ЕАЭС
берётся из гражданства члена артели."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_tax.models.labor_payout import EAEU_CITIZEN


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Payout = env['coop.tax.labor.payout'].with_context(active_test=False)
    for payout in Payout.search([('resident', '=', False), ('work_place', '=', 'ru')]):
        code = payout.partner_id._coop_citizenship().code
        if code in EAEU_CITIZEN:
            payout.eaeu = True
    pays = Payout.search([('resident', '=', False), ('work_place', '=', 'ru')])
    env.add_to_compute(Payout._fields['ndfl_amount'], pays)
    env.flush_all()
