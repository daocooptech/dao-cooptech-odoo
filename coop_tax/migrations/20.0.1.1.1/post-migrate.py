# -*- coding: utf-8 -*-
"""Решение 515: свои доходы в натуральной форме у витринного человека —
без них реестр у него пуст."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_tax.hooks import demo_natural_income_showcase


def migrate(cr, version):
    demo_natural_income_showcase(api.Environment(cr, SUPERUSER_ID, {}))
