# -*- coding: utf-8 -*-
"""Решение 515: способ оплаты у задач и реестр доходов в натуральной форме
на уже установленном модуле — то же, что при установке."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_tax.hooks import demo_natural_income


def migrate(cr, version):
    demo_natural_income(api.Environment(cr, SUPERUSER_ID, {}))
