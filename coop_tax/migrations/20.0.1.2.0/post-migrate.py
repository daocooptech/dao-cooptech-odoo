# -*- coding: utf-8 -*-
"""Решение 517: лимит кооперативных выплат по годам на уже установленном
модуле — то же, что при установке."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_tax.hooks import demo_payout_limits


def migrate(cr, version):
    demo_payout_limits(api.Environment(cr, SUPERUSER_ID, {}))
