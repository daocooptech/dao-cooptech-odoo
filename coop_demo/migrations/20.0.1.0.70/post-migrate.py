# -*- coding: utf-8 -*-
"""Виды пая в портфеле (решение 512): дивиденды по дополнительному паю,
приращённый пай, сбережения в КПК."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_share_kinds


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    load_share_kinds.load_share_kinds(env)
