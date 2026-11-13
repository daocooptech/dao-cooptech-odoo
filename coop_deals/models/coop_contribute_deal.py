# -*- coding: utf-8 -*-
"""«Предложить сделку» из окна вклада (решение 676).

Нечлену вклад в кооперативный проект закрыт, но отдать проекту технику,
помещение или работу он может — сделкой с инициатором: аренда, продажа,
дар, работа по договору. Заводится обращение по сделке, как при отклике
на объявление.
"""
from odoo import _, fields, models
from odoo.exceptions import UserError


class CoopContributeDeal(models.TransientModel):
    _inherit = 'coop.project.contribute'

    deal_way = fields.Selection([
        ('rent', 'Аренда'),
        ('sale', 'Продажа'),
        ('service', 'Работа или услуга по договору'),
        ('gift', 'Дар'),
    ], string='Как передаёте', default='rent')
    deal_name = fields.Char(string='Что именно')
    deal_amount = fields.Monetary(
        string='Сумма', currency_field='currency_id')

    def action_coop_propose_deal(self):
        self.ensure_one()
        project = self.project_id
        me = self.env.user._coop_acting_partner()
        if project.partner_id == me:
            raise UserError(_('Это ваш проект.'))
        what = self.deal_name or self.name
        if not what:
            raise UserError(_('Напишите, что именно предлагаете проекту.'))
        deal = self.env['coop.deal'].sudo().create({
            'name': what,
            'subject': 'service' if self.deal_way == 'service' else 'resource',
            'way': self.deal_way or 'rent',
            'party_a_id': me.id,
            'party_b_id': project.partner_id.id,
            'role_a': _('Передаёт'),
            'role_b': _('Принимает'),
            'author_id': self.env.user.partner_id.id,
            'project_id': project.id,
            'amount': self.deal_amount or self.value or 0.0,
            'state': 'lead',
        })
        body = _('Предложение сделки по проекту «%(project)s»: %(what)s '
                 'от %(who)s. Обращение %(number)s.',
                 project=project.name, what=what, who=me.display_name,
                 number=deal.number or '')
        self.env['coop.notification']._notify(
            project.partner_id, body, record=project, kind='project')
        project.sudo().message_post(body=body)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'coop.deal',
            'res_id': deal.id,
            'view_mode': 'form',
            'target': 'current',
        }
