# -*- coding: utf-8 -*-
"""Краудсорсинг для всех проектов (решение 690).

Задачи проекта оплачиваются только токенами этого проекта: у нашего
проекта (ДАО КООПТЕХ) это токены услуг платформы из фонда задач, у
остальных — их собственные токены. Экономику своего токена каждый
проект раскрывает сам, в рамках законов своей страны; платформа общих
правил токена проекта не задаёт. Учёт токенов проекта — в базе узла,
как и токенов за задачи платформы (решение 668).
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopProjectToken(models.Model):
    _inherit = 'coop.project'

    coop_token_name = fields.Char(
        string='Токен проекта',
        help='Как проект называет свой токен. Им оплачиваются задачи проекта в краудсорсинге.')
    coop_token_symbol = fields.Char(string='Обозначение', help='Коротко, до шести знаков.')
    coop_token_economy = fields.Html(
        string='Экономика токена',
        help='Что даёт токен, чем обеспечен, как погашается. Проект раскрывает это сам — '
             'в рамках законов своей страны.')
    coop_token_issued = fields.Integer(string='Начислено за задачи, токенов',
                                       compute='_compute_coop_token_issued')

    def _compute_coop_token_issued(self):
        Move = self.env['coop.project.token.move'].sudo()
        for project in self:
            project.coop_token_issued = sum(Move.search(
                [('project_id', '=', project.id)]).mapped('amount')) if project.id else 0

    def _coop_token_unit(self):
        self.ensure_one()
        return self.coop_token_symbol or _('токенов проекта')


class CoopProjectTokenMove(models.Model):
    """Начисление токенов проекта за принятую задачу — учёт в узле."""
    _name = 'coop.project.token.move'
    _description = 'Начисление токенов проекта'
    _order = 'date desc, id desc'

    project_id = fields.Many2one('coop.project', string='Проект', required=True,
                                 index=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Кому', required=True, index=True)
    amount = fields.Integer(string='Токенов', required=True)
    task_id = fields.Many2one('coop.bounty.task', string='Задача', index=True, ondelete='set null')
    date = fields.Date(string='Когда', required=True, default=fields.Date.context_today)
    description = fields.Char(string='За что')


class CoopBountyTaskCrowd(models.Model):
    _inherit = 'coop.bounty.task'

    payment_label = fields.Char(string='Оплата', compute='_compute_payment_label')
    token_unit = fields.Char(compute='_compute_payment_label')

    @api.depends('payer_kind', 'project_id.coop_token_name', 'project_id.coop_token_symbol')
    def _compute_payment_label(self):
        for task in self:
            if task.payer_kind == 'platform':
                task.payment_label = _('Токены услуг платформы')
                task.token_unit = _('токенов')
            elif task.project_id:
                task.payment_label = task.project_id.coop_token_name or (
                    _('Токены проекта «%s»') % task.project_id.name)
                task.token_unit = task.project_id._coop_token_unit()
            else:
                task.payment_label = _('Токены проекта')
                task.token_unit = _('токенов проекта')

    @api.model
    def _coop_our_project(self):
        return self.env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)

    def _coop_check_publishable(self):
        """Только токены своего проекта (решение 690): способ ставится сам."""
        self.ensure_one()
        if self.payer_kind == 'platform':
            code = 'tokens'
            if not self.project_id:
                self.project_id = self._coop_our_project()
        else:
            code = 'project_tokens'
            if not self.project_id:
                raise UserError(_('Укажите проект: задачи краудсорсинга оплачиваются токенами проекта.'))
            if not self.project_id.coop_token_name:
                raise UserError(_(
                    'Сначала опишите токен проекта «%s» — название и экономику токена, '
                    'вкладка «Токен проекта» в карточке проекта.') % self.project_id.name)
        method = self.env['coop.bounty.method'].sudo().search([('code', '=', code)], limit=1)
        self.write({'allowed_method_ids': [(6, 0, method.ids)], 'share_percent': 0})
        return super()._coop_check_publishable()
