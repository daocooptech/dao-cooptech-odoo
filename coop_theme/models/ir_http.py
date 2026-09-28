# -*- coding: utf-8 -*-
from odoo import models

from ..node_path import NODE_PATH


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Имя узла для браузера: роутер строит по нему адреса /nn1/…"""
        info = super().session_info()
        info['coop_node_path'] = NODE_PATH
        return info
