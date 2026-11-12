# -*- coding: utf-8 -*-
"""Video in showcase carousels (task 424). Idempotent."""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_media_video


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    load_media_video.load_media_video(env)
