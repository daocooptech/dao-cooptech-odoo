# -*- coding: utf-8 -*-
"""Лента снимков под главным снимком ресурса (№ 397). Идемпотентно."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_resource_gallery


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_resource_gallery.load_resource_gallery(env)
