# -*- coding: utf-8 -*-
"""Пути «Стать пайщиком» и «Работать» в окне «Участвовать» (задача 445).

Путь пайщика виден всегда; если заявление не подать — рядом причина и
что делать (решение 677). Работа — вакансии проекта и организации:
найм — не основание вступления (решение 678).
"""
from odoo import _, api, fields, models


class CoopContributeJoin(models.TransientModel):
    _inherit = 'coop.project.contribute'

    join_block = fields.Selection([
        ('member', 'Уже член'),
        ('applied', 'Заявление подано'),
        ('closed', 'Не принимает'),
        ('no_charter', 'Нет устава'),
    ], compute='_compute_join_block')
    join_block_note = fields.Char(compute='_compute_join_block')
    vacancy_count = fields.Integer(compute='_compute_vacancy_count')
    # Путь «Работать» внутри окна (задача 445, кусок 3): вакансии проекта,
    # за ними — организации, с «Откликнуться» в строке.
    work_vacancy_ids = fields.Many2many(
        'coop.vacancy', string='Вакансии', compute='_compute_vacancy_count')

    @api.depends('project_id')
    def _compute_join_block(self):
        for wizard in self:
            org = wizard.project_id.partner_id
            block, note = org._coop_join_block() if org else (False, False)
            wizard.join_block = block
            wizard.join_block_note = note

    def _coop_vacancy_domain(self):
        self.ensure_one()
        project = self.project_id
        return [('state', '=', 'published'), '|',
                ('coop_project_id', '=', project.id),
                ('partner_id', '=', project.partner_id.id)]

    @api.depends('project_id')
    def _compute_vacancy_count(self):
        Vacancy = self.env['coop.vacancy']
        for wizard in self:
            if not wizard.project_id:
                wizard.vacancy_count = 0
                wizard.work_vacancy_ids = Vacancy
                continue
            found = Vacancy.sudo().search(wizard._coop_vacancy_domain())
            # Сперва вакансии этого проекта, потом остальные организации.
            project = wizard.project_id
            found = found.sorted(
                lambda v: (v.coop_project_id != project, v.id))
            wizard.vacancy_count = len(found)
            wizard.work_vacancy_ids = Vacancy.browse(found.ids)

    def action_coop_join_org(self):
        """«Читать условия» — заявление в три шага, «Назад» — сюда."""
        self.ensure_one()
        action = self.project_id.partner_id.action_coop_join()
        action['context'] = dict(action.get('context') or {},
                                 default_project_id=self.project_id.id)
        return action

    def action_coop_follow_org(self):
        self.ensure_one()
        self.project_id.partner_id.sudo().message_subscribe(
            partner_ids=self.env.user.partner_id.ids)
        return {'type': 'ir.actions.act_window_close'}

    def action_coop_withdraw_join(self):
        self.ensure_one()
        mine = self.project_id.partner_id._coop_my_membership()
        if mine and mine.state == 'applied':
            mine.action_withdraw()
        return self.project_id.action_contribute()

    def action_coop_vacancies(self):
        """Вакансии проекта и организации — каталогом, с откликом."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Вакансии — «%s»') % self.project_id.name,
            'res_model': 'coop.vacancy',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': self._coop_vacancy_domain(),
            'target': 'current',
        }
