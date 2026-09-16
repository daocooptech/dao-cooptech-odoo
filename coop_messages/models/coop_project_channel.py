# -*- coding: utf-8 -*-
"""Состав чата проекта — инициатор и те, чей вклад принят."""

from odoo import api, models


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

    def _coop_channel_specs(self):
        """Одна переписка на проект: название — как в каталоге."""
        self.ensure_one()
        return [{
            'kind': 'project',
            'name': self.name,
            'subtitle': self.city or False,
            'partners': self._coop_channel_partners(),
        }]

    def _coop_channel_owners(self, kind=None):
        """Инициатор проекта: он завёл проект, ему и отвечать за его
        переписку. Вкладчики в ней участвуют, но не распоряжаются."""
        self.ensure_one()
        return self.partner_id

    @api.model_create_multi
    def create(self, vals_list):
        проекты = super().create(vals_list)
        проекты._coop_ensure_channel()
        проекты._coop_sync_channels()
        return проекты

    def write(self, vals):
        res = super().write(vals)
        if 'partner_id' in vals:
            self._coop_sync_channels()
        return res


class CoopProjectContribution(models.Model):
    """Приняли вклад — человек вошёл в разговор проекта.

    Хук на вкладе, а не на проекте: состав меняется именно здесь, и
    отсюда же видно, что изменилось — принятие, отзыв, удаление.
    """

    _inherit = 'coop.project.contribution'

    @api.model_create_multi
    def create(self, vals_list):
        вклады = super().create(vals_list)
        вклады.mapped('project_id')._coop_sync_channels()
        return вклады

    def write(self, vals):
        проекты_до = self.mapped('project_id')
        res = super().write(vals)
        if {'state', 'partner_id', 'project_id'} & set(vals):
            (проекты_до | self.mapped('project_id'))._coop_sync_channels()
        return res

    def unlink(self):
        проекты = self.mapped('project_id')
        res = super().unlink()
        проекты._coop_sync_channels()
        return res
