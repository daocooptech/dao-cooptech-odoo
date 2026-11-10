# -*- coding: utf-8 -*-
"""Единицы измерения объявлений — справочник с модерацией.

Решение 634, владелец 10.11.2026: единицу товара выбирает продавец; нет
нужной — предлагает свою, она проходит модерацию и попадает в справочник
(общий приём «свой вариант + модерация», решения 601–602).

Предложенная единица сразу доступна автору (иначе объявление не
сохранить), а остальным — только после одобрения платформой.
"""
from odoo import api, fields, models


class CoopResourceUom(models.Model):
    _name = 'coop.resource.uom'
    _description = 'Единица измерения ресурса'
    _order = 'sequence, name'

    name = fields.Char(string='Единица', required=True)
    sequence = fields.Integer(string='Порядок', default=100)
    state = fields.Selection([
        ('approved', 'В справочнике'),
        ('proposed', 'На модерации'),
        ('rejected', 'Отклонена'),
    ], string='Состояние', default='approved', required=True, index=True)
    proposed_by_id = fields.Many2one(
        'res.partner', string='Предложил', ondelete='set null')

    _name_uniq = models.Constraint('unique(name)', 'Такая единица уже есть.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = ' '.join((vals.get('name') or '').split())
        return super().create(vals_list)

    @api.model
    def coop_choices(self):
        """Единицы для выбора: одобренные и свои предложенные."""
        partner = self.env.user.partner_id
        found = self.sudo().search([
            '|', ('state', '=', 'approved'),
            '&', ('state', '=', 'proposed'), ('proposed_by_id', '=', partner.id),
        ])
        return [{'name': unit.name, 'proposed': unit.state == 'proposed'}
                for unit in found]

    @api.model
    def coop_propose(self, name):
        """Свой вариант: завести единицу на модерацию, если такой нет.

        Возвращает имя, под которым единица записана (у двойника с другим
        регистром — имя из справочника), и признак, что она ещё на
        модерации.
        """
        name = ' '.join((name or '').split())
        if not name:
            return False
        # Регистр сводим в Python: `ilike` базы на кириллице зависит от
        # локали кластера (на стенде с локалью C «БУХТА» ≠ «бухта»).
        key = name.casefold()
        unit = next((u for u in self.sudo().search([]) if u.name.casefold() == key),
                    self.browse())
        if not unit:
            unit = self.sudo().create({
                'name': name[:40],
                'state': 'proposed',
                'proposed_by_id': self.env.user.partner_id.id,
            })
        return {'name': unit.name, 'proposed': unit.state == 'proposed'}

    def action_approve(self):
        self.write({'state': 'approved'})
        return True

    def action_reject(self):
        self.write({'state': 'rejected'})
        return True
