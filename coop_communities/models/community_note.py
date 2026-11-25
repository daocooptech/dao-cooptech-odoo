# -*- coding: utf-8 -*-
"""Заметки и задачи группы — её действующим участникам (решение 696)."""
from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    coop_space = fields.Selection(
        selection_add=[('community', 'Группа')], ondelete={'community': 'set default'})
    coop_community_id = fields.Many2one(
        'coop.community', string='Группа', index='btree_not_null', ondelete='set null',
        help='Запись видят все действующие участники группы.')

    @api.model
    def _coop_space_fields(self):
        return dict(super()._coop_space_fields(), community='coop_community_id')

    def _coop_space_member(self):
        self.ensure_one()
        if self.coop_space == 'community':
            return bool(self.env['coop.community.member'].sudo().search_count([
                ('community_id', '=', self.coop_community_id.id),
                ('partner_id', '=', self.env.user.partner_id.id),
                ('state', '=', 'active')], limit=1))
        return super()._coop_space_member()

    def write(self, vals):
        if vals.get('coop_space', 'community') != 'community':
            vals = dict(vals, coop_community_id=False)
        return super().write(vals)
