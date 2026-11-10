# -*- coding: utf-8 -*-
"""Внести нематериальный актив в проект с карточки самого актива (№ 395).

Раньше актив вкладывался только со страницы проекта и только в ответ на
строку потребности в нематериальном. Владелец 10.11.2026: нематериальные
активы должны участвовать в проектах — и с карточки актива, и от имени
организации-правообладателя. Окно здесь собирает вклад из актива и проекта
и отдаёт его тому же `action_offer`, что и обычное «Участвовать»: правила
(кто принимает, что проект собирает, нельзя вкладываться в свой проект)
остаются в одном месте.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopIntangibleToProject(models.TransientModel):
    _name = 'coop.intangible.to.project'
    _description = 'Внести актив в проект'

    intangible_id = fields.Many2one(
        'coop.intangible', string='Актив', required=True, readonly=True)
    project_id = fields.Many2one(
        'coop.project', string='Проект', required=True,
        domain="[('id', 'in', project_ids)]",
        help='Проект, который собирает вклады или добирает открытую '
             'потребность. Свой проект в список не попадает.')
    project_ids = fields.Many2many(
        'coop.project', string='Подходящие проекты', compute='_compute_project_ids')
    currency_id = fields.Many2one(
        related='project_id.currency_id', readonly=True)
    value = fields.Monetary(
        string='Оценка, ₽', currency_field='currency_id', required=True,
        help='Денежная оценка вклада по соглашению сторон. По умолчанию — '
             'остаточная стоимость актива.')
    ownership_kind = fields.Selection([
        ('property', 'В собственность'),
        ('use', 'В пользование'),
    ], string='Передаётся', default='use', required=True,
        help='Право отдают насовсем или даёт проект право пользоваться — '
             'лицензией. Для товарного знака и патента важно, чьё оно '
             'остаётся после проекта.')
    note = fields.Text(string='Пара слов инициатору')

    @api.depends('intangible_id')
    def _compute_project_ids(self):
        Project = self.env['coop.project'].sudo()
        for wizard in self:
            owner = wizard.intangible_id.owner_id
            wizard.project_ids = Project.search([
                ('state', 'in', ('gathering', 'running')),
                ('partner_id', '!=', owner.id),
            ], limit=300)

    @api.onchange('intangible_id')
    def _onchange_intangible_id(self):
        for wizard in self:
            if wizard.intangible_id.residual_value:
                wizard.value = wizard.intangible_id.residual_value

    def action_offer(self):
        self.ensure_one()
        asset = self.intangible_id
        if asset.state != 'active':
            raise UserError(_('Вносят действующее право: у «%s» права ещё не подтверждены '
                              'или охрана закончилась.') % asset.name)
        # Открытая строка потребности на этот же актив — вклад закрывает её.
        need = self.env['coop.intangible.need'].sudo().search([
            ('project_id', '=', self.project_id.id),
            ('intangible_id', '=', asset.id), ('state', '=', 'open')], limit=1)
        wizard = self.env['coop.project.contribute'].create({
            'project_id': self.project_id.id,
            'kind': 'knowledge',
            'name': asset.name,
            'value': self.value,
            'ownership_kind': self.ownership_kind,
            'note': self.note,
            'intangible_id': asset.id,
            'need_intangible_id': need.id or False,
        })
        return wizard.action_offer()


class CoopIntangibleProjects(models.Model):
    """Карточка актива: куда внесён и можно ли внести ещё."""
    _inherit = 'coop.intangible'

    project_offer_count = fields.Integer(
        string='Проектов', compute='_compute_project_offer_count')

    @api.depends('contribution_ids.state')
    def _compute_project_offer_count(self):
        for asset in self:
            asset.project_offer_count = len(set(asset.contribution_ids.filtered(
                lambda c: c.state in ('offered', 'accepted')).mapped('project_id').ids))

    def action_to_project(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Внести в проект: %s') % self.name,
            'res_model': 'coop.intangible.to.project',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_intangible_id': self.id,
                        'default_value': self.residual_value or 0.0},
        }


class ResPartnerIntangibleProjects(models.Model):
    """Карточка организации: её активы в проектах."""
    _inherit = 'res.partner'

    coop_asset_project_count = fields.Integer(
        string='Активов в проектах', compute='_compute_coop_asset_project_count')

    def _compute_coop_asset_project_count(self):
        """Публичная величина, как число проектов: через sudo."""
        Contribution = self.env['coop.project.contribution'].sudo()
        counts = {}
        if self.ids:
            for owner, count in Contribution._read_group(
                    [('intangible_id.owner_id', 'in', self.ids),
                     ('state', 'in', ('offered', 'accepted'))],
                    ['intangible_id.owner_id'], ['__count']):
                counts[owner.id] = count
        for partner in self:
            partner.coop_asset_project_count = counts.get(partner.id, 0)

    def action_coop_assets_in_projects(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Активы в проектах — %s', self.display_name),
            'res_model': 'coop.project.contribution',
            'view_mode': 'list,form',
            'domain': [('intangible_id.owner_id', '=', self.id),
                       ('state', 'in', ('offered', 'accepted'))],
        }
