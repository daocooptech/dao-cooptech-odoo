# -*- coding: utf-8 -*-
"""Решения 514, 516: выплаты членам артелей за трудовое участие на уже
установленном модуле — то же, что при установке."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_tax.hooks import demo_labor_payouts


def migrate(cr, version):
    demo_labor_payouts(api.Environment(cr, SUPERUSER_ID, {}))
