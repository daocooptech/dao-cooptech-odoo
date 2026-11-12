# -*- coding: utf-8 -*-
"""Заметки — на штатных To-Do движка (задача 426).

Владелец 12.11.2026: «надо, чтобы у всех были свои заметки и дела»;
вариант — штатный To-Do (`project_todo`): отдельного модуля заметок в
Odoo 20 нет, старый `note` слит в To-Do. Заметка — личная задача
`project.task` без проекта движка; здесь к ней добавлена ссылка на
проект платформы, чтобы на странице проекта были видны свои заметки
по нему. Меню — «Проекты → Заметки» (владелец 12.11.2026).
"""
from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    coop_project_id = fields.Many2one(
        'coop.project', string='Проект платформы', index='btree_not_null',
        ondelete='set null',
        help='К какому проекту платформы относится заметка.')


class CoopProject(models.Model):
    _inherit = 'coop.project'

    coop_note_ids = fields.Many2many(
        'project.task', string='Мои заметки', compute='_compute_coop_notes')
    coop_note_count = fields.Integer(
        string='Заметок', compute='_compute_coop_notes')

    def _coop_note_domain(self):
        return [('coop_project_id', 'in', self.ids),
                ('user_ids', 'in', [self.env.uid]),
                ('project_id', '=', False), ('parent_id', '=', False)]

    @api.depends_context('uid')
    def _compute_coop_notes(self):
        ids = [r.id for r in self if isinstance(r.id, int)]
        notes = self.env['project.task'].search(
            self.browse(ids)._coop_note_domain()) if ids else self.env['project.task']
        for record in self:
            mine = notes.filtered(lambda n: n.coop_project_id.id == record.id)
            record.coop_note_ids = mine
            record.coop_note_count = len(mine)

    def action_coop_notes(self):
        """Мои заметки по проекту — тот же список To-Do, с отбором."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'coop_projects.action_coop_notes')
        action['name'] = 'Заметки: %s' % self.name
        action['domain'] = self._coop_note_domain()
        action['context'] = dict(
            self.env.context, default_coop_project_id=self.id,
            default_project_id=False, search_default_open_tasks=1,
            list_view_ref='project_todo.project_task_view_todo_tree',
            show_task_options=False)
        return action

    def action_coop_new_note(self):
        """Новая заметка к проекту — сразу формой To-Do."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Новая заметка',
            'res_model': 'project.task',
            'view_mode': 'form',
            'views': [(self.env.ref('project_todo.project_task_view_todo_form').id, 'form')],
            'target': 'current',
            'context': {'default_coop_project_id': self.id, 'default_project_id': False,
                        'default_user_ids': [(6, 0, [self.env.uid])],
                        'default_name': 'Заметка: %s' % self.name},
        }
