# -*- coding: utf-8 -*-
"""Держатели токена проекта и запрет смены вида (№ 485, решение 704).

Список держателей с количеством видят сами держатели и инициатор;
остальные — только число держателей и сколько начислено. После первого
начисления вид токена не меняется: держатель получил определённое право.
"""
from odoo import _, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import SQL


class CoopProjectTokenHolder(models.Model):
    _name = 'coop.project.token.holder'
    _description = 'Держатель токена проекта'
    _auto = False
    _order = 'amount desc, id'
    _rec_name = 'partner_id'
    _depends = {
        'coop.project.token.move': ['project_id', 'partner_id', 'amount'],
        'coop.token.transaction': ['partner_id', 'amount', 'kind', 'res_model'],
    }

    project_id = fields.Many2one('coop.project', string='Проект', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Держатель', readonly=True)
    amount = fields.Integer(string='Токенов', readonly=True)

    @property
    def _table_sql(self):
        # Наш проект платит токенами услуг платформы: держатели — те, кому
        # они начислены за задачи; пополнения и траты кошелька не входят.
        self.env['coop.project.token.move'].flush_model()
        self.env['coop.token.transaction'].flush_model()
        return SQL("""(
            SELECT 2 * min(m.id) AS id, m.project_id, m.partner_id,
                   sum(m.amount)::int AS amount
              FROM coop_project_token_move m
             GROUP BY m.project_id, m.partner_id
            HAVING sum(m.amount) > 0
             UNION ALL
            SELECT 2 * min(t.id) + 1, d.res_id, t.partner_id, sum(t.amount)::int
              FROM coop_token_transaction t
              JOIN ir_model_data d
                ON d.module = 'coop_bounty' AND d.name = 'project_cooptech'
               AND d.model = 'coop.project'
             WHERE t.kind = 'grant'
               AND t.res_model IN ('coop.bounty.task', 'project.task')
             GROUP BY d.res_id, t.partner_id
            HAVING sum(t.amount) > 0
        )""")


class CoopProjectTokenHolders(models.Model):
    _inherit = 'coop.project'

    coop_holder_ids = fields.One2many(
        'coop.project.token.holder', 'project_id', string='Держатели', readonly=True)
    coop_holder_count = fields.Integer(
        string='Держателей', compute='_compute_coop_holder_count', compute_sudo=True)

    def _compute_coop_holder_count(self):
        counts = {project.id: count for project, count in
                  self.env['coop.project.token.holder'].sudo()._read_group(
                      [('project_id', 'in', self._origin.ids)], ['project_id'], ['__count'])}
        for project in self:
            project.coop_holder_count = counts.get(project._origin.id, 0)

    def _coop_token_granted(self):
        """Начислял ли проект свой токен хоть раз."""
        self.ensure_one()
        if self == self.env['coop.bounty.task']._coop_our_project():
            return bool(self.env['coop.project.token.holder'].sudo().search_count(
                [('project_id', '=', self.id)], limit=1))
        return bool(self.env['coop.project.token.move'].sudo().search_count(
            [('project_id', '=', self.id), ('amount', '>', 0)], limit=1))

    def write(self, vals):
        if 'coop_token_kind' in vals:
            for project in self:
                if project.coop_token_kind and project.coop_token_kind != vals['coop_token_kind'] \
                        and project._coop_token_granted():
                    raise ValidationError(_(
                        'Токены проекта «%s» уже начислены — вид токена не меняется: '
                        'держатели получили определённое право.') % project.name)
        return super().write(vals)
