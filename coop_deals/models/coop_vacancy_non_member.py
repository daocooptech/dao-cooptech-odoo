# -*- coding: utf-8 -*-
"""Труд нечлена по вакансии проекта — сделкой (решения 659 п. 3, 676).

Вклад в кооперативный проект вносит только член. Нечлена, утверждённого
на вакансию проекта, в паи не пускаем: его работа — сделка «Работа по
вакансии» между ним и инициатором, с оплатой по оценке вакансии.
"""
from odoo import _, fields, models


class CoopVacancyApplicationDeal(models.Model):
    _inherit = 'coop.vacancy.application'

    def _accept_non_member(self, project):
        vacancy = self.vacancy_id
        value = vacancy.contribution_value or 0
        deal = self.env['coop.deal'].sudo().create({
            'name': vacancy.name,
            'subject': 'work',
            'way': 'job',
            'party_a_id': self.partner_id.id,
            'party_b_id': project.partner_id.id,
            'role_a': _('Исполнитель'),
            'role_b': _('Заказчик'),
            'author_id': self.env.user.partner_id.id,
            'project_id': project.id,
            'vacancy_id': vacancy.id,
            'amount': value,
            'state': 'draft',
        })
        self.env['coop.notification']._notify(
            self.partner_id, _(
                'Отклик на «%(what)s» утверждён. Вы не член «%(org)s», '
                'поэтому работа оформлена сделкой %(number)s, а не паем.',
                what=vacancy.name, org=project.partner_id.display_name,
                number=deal.number or ''),
            record=deal, kind='deal')
        self._close_vacancy_after_accept(
            {}, _('нечлен — работа оформлена сделкой %s') % (deal.number or ''))
        return deal
