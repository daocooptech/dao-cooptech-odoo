# -*- coding: utf-8 -*-
"""«Вступить в кооператив» из окна вклада (решение 676)."""
from odoo import models


class CoopContributeJoin(models.TransientModel):
    _inherit = 'coop.project.contribute'

    def action_coop_join_org(self):
        """То же окно заявления, что и на странице организации."""
        self.ensure_one()
        return self.project_id.partner_id.action_coop_join()
