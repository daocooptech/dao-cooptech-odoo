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
        people = self.partner_id
        contributions = self.contribution_ids.filtered(lambda c: c.state == 'accepted')
        people |= contributions.mapped('partner_id')
        return people.coop_power_holders('represent')

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
        projects = super().create(vals_list)
        projects._coop_ensure_channel()
        projects._coop_sync_channels()
        return projects

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
        contributions = super().create(vals_list)
        contributions.mapped('project_id')._coop_sync_channels()
        return contributions

    def write(self, vals):
        projects_before = self.mapped('project_id')
        res = super().write(vals)
        if {'state', 'partner_id', 'project_id'} & set(vals):
            (projects_before | self.mapped('project_id'))._coop_sync_channels()
        return res

    def unlink(self):
        projects = self.mapped('project_id')
        res = super().unlink()
        projects._coop_sync_channels()
        return res
