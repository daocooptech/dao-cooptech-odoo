# -*- coding: utf-8 -*-
"""Потребность проекта в нематериальном активе.

Решение владельца 632 от 28.10.2026: в смете проекта четыре вида — и
нематериальные в ней есть наравне с вещами и трудом. Сделаны они не
четвёртым видом каталога ресурсов, а отдельным списком на записях модуля
«Нематериальные»: у кооператива просят не «что-то из ноу-хау вообще», а
конкретную рецептуру, программу или товарный знак, и у этой записи уже
есть правообладатель, оценка и правовое основание.

Строка живёт отдельной моделью, а не полем у актива: актив принадлежит
правообладателю и переживает проект, а потребность — свойство проекта и
умирает вместе с ним.
"""
from odoo import _, api, fields, models


class CoopIntangibleNeed(models.Model):
    """Что проекту нужно из нематериального."""
    _name = 'coop.intangible.need'
    _description = 'Потребность проекта в нематериальном активе'
    _order = 'project_id, id'

    project_id = fields.Many2one(
        'coop.project', string='Проект', required=True, index=True,
        ondelete='cascade')
    intangible_id = fields.Many2one(
        'coop.intangible', string='Актив', required=True, index=True,
        ondelete='restrict',
        help='Что именно просит проект. Не «знания вообще», а конкретная '
             'рецептура, программа или знак: только у записи есть '
             'правообладатель и основание охраны.')
    price = fields.Monetary(
        string='Оценка, ₽', currency_field='currency_id',
        help='Денежная оценка потребности: по ней считается пай или доля '
             'того, кто её закроет.')
    currency_id = fields.Many2one(
        related='project_id.currency_id', string='Валюта', readonly=True)
    state = fields.Selection([
        ('open', 'Открыта'),
        ('closed', 'Закрыта'),
        ('cancelled', 'Снята'),
    ], string='Состояние', default='open', required=True, index=True)
    note = fields.Text(string='Пояснение')
    manager_id = fields.Many2one(
        'res.partner', string='Ответственный',
        help='Кто решает по этой потребности. Пусто — решает инициатор '
             'проекта.')
    closed_by_id = fields.Many2one(
        'res.partner', string='Закрыл', readonly=True, copy=False)
    closed_on = fields.Datetime(string='Закрыта', readonly=True, copy=False)

    def action_close(self):
        """Закрыть потребность — вручную инициатором или при принятии вклада."""
        for need in self:
            if need.state == 'open':
                need.write({'state': 'closed'})
        return True

    def action_cancel(self):
        self.filtered(lambda n: n.state == 'open').write({'state': 'cancelled'})
        return True

    def action_join(self):
        """«Участвовать» из строки потребности в нематериальном.

        Открывает то же окно вклада, что и у вещей и труда: второй способ
        ответить на потребность человек искать не должен.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Участие: %s') % self.intangible_id.name,
            'res_model': 'coop.project.contribute',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_project_id': self.project_id.id,
                'default_need_intangible_id': self.id,
                'default_name': self.intangible_id.name,
                'default_value': self.price,
                'default_kind': 'knowledge',
            },
        }

    def _need_deciders(self):
        """Кто вправе закрыть: ответственный за строку и инициатор проекта."""
        self.ensure_one()
        deciders = self.manager_id | self.project_id.partner_id
        return deciders


class CoopProjectIntangible(models.Model):
    """Четвёртый список сметы — на странице проекта."""
    _inherit = 'coop.project'

    need_intangible_ids = fields.One2many(
        'coop.intangible.need', 'project_id',
        string='Нематериальные потребности',
        domain=[('state', '=', 'open')])
    need_intangible_count = fields.Integer(
        string='Нематериальных потребностей',
        compute='_compute_need_intangible_count')

    @api.depends('need_intangible_ids')
    def _compute_need_intangible_count(self):
        for project in self:
            project.need_intangible_count = len(project.need_intangible_ids)


class CoopProjectContributionIntangible(models.Model):
    """Вклад может быть внесён нематериальным активом."""
    _inherit = 'coop.project.contribution'

    intangible_id = fields.Many2one(
        'coop.intangible', string='Нематериальный актив', index=True,
        ondelete='set null',
        help='Актив, которым закрывают потребность проекта в нематериальном.')
    need_intangible_id = fields.Many2one(
        'coop.intangible.need', string='Потребность в НМА', index=True,
        ondelete='set null')

    def action_accept(self):
        """Приняли вклад — потребность в НМА закрывается тем же действием."""
        result = super().action_accept()
        for contribution in self:
            need = contribution.need_intangible_id
            if need and need.state == 'open':
                need.write({
                    'state': 'closed',
                    'closed_by_id': contribution.partner_id.id,
                    'closed_on': fields.Datetime.now(),
                })
        return result


class CoopContributeWizardIntangible(models.TransientModel):
    """Окно вклада: свой нематериальный актив вместо описания словами."""
    _inherit = 'coop.project.contribute'

    need_intangible_id = fields.Many2one(
        'coop.intangible.need', string='Потребность в нематериальном',
        readonly=True)
    intangible_id = fields.Many2one(
        'coop.intangible', string='Мой актив',
        domain="[('id', 'in', my_intangible_ids)]",
        help='Что из своих нематериальных активов вкладываете.')
    my_intangible_ids = fields.Many2many(
        'coop.intangible', string='Мои нематериальные',
        compute='_compute_my_intangibles')

    @api.depends('need_intangible_id')
    @api.depends_context('uid')
    def _compute_my_intangibles(self):
        """Только свои активы: чужим вкладом закрывать потребность нельзя —
        правообладатель не соглашался."""
        mine = self.env.user.coop_actor_partner_ids
        found = self.env['coop.intangible'].search(
            [('owner_id', 'in', mine.ids)], limit=200)
        for wizard in self:
            wizard.my_intangible_ids = found

    @api.onchange('intangible_id')
    def _onchange_intangible_id(self):
        for wizard in self:
            asset = wizard.intangible_id
            if not asset:
                continue
            if not wizard.name:
                wizard.name = asset.name
            if not wizard.value and asset.residual_value:
                wizard.value = asset.residual_value

    def _coop_offer_values(self):
        values = super()._coop_offer_values()
        if self.intangible_id:
            values['intangible_id'] = self.intangible_id.id
        if self.need_intangible_id:
            values['need_intangible_id'] = self.need_intangible_id.id
        return values
