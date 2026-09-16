# -*- coding: utf-8 -*-
"""Состав чата проекта — инициатор и те, чей вклад принят."""

from odoo import models


class CoopProject(models.Model):
    _name = 'coop.project'
    _inherit = ['coop.project', 'coop.channel.sync']

    def _coop_channel_partners(self):
        """Инициатор плюс принятые вклады.

        Тот же состав, что у подписчиков проекта: кто вложился — тот и
        участвует в разговоре. Заявленный, но не принятый вклад в чат не
        пускает: пока вклад не принят, человек в проекте не участвует.
        """
        self.ensure_one()
        люди = self.partner_id
        вклады = self.contribution_ids.filtered(lambda c: c.state == 'accepted')
        люди |= вклады.mapped('partner_id')
        return люди.coop_power_holders('represent')
