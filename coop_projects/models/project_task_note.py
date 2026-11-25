# -*- coding: utf-8 -*-
"""Заметки — на штатных To-Do движка (задача 426).

Владелец 12.11.2026: «надо, чтобы у всех были свои заметки и дела»;
вариант — штатный To-Do (`project_todo`): отдельного модуля заметок в
Odoo 20 нет, старый `note` слит в To-Do. Заметка — личная задача
`project.task` без проекта движка; здесь к ней добавлена ссылка на
проект платформы, чтобы на странице проекта были видны свои заметки
по нему. Меню — «Моя страница → Заметки»
и «Задачи» (решение 705, пункты — в `coop_profile`).
"""
import html
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    coop_project_id = fields.Many2one(
        'coop.project', string='Проект платформы', index='btree_not_null',
        ondelete='set null',
        help='К какому проекту платформы относится заметка.')
    coop_kind = fields.Selection([
        ('note', 'Заметка'),
        ('task', 'Задача'),
    ], string='Вид', default='note', required=True, index=True,
        help='Заметка — текст для памяти, задача — то, что надо сделать к сроку.')
    # Видимость — по пространству (решение 696), а не по ссылке на проект:
    # ссылка на проект была и у личных заметок, и читать их команда
    # проекта не должна.
    coop_space = fields.Selection([
        ('personal', 'Личное'),
        ('project', 'Проект'),
    ], string='Пространство', default='personal', required=True, index=True,
        help='Личное видите только вы и исполнители, остальное — участники '
             'проекта, организации или группы.')

    # Вид «заметки на доске» (владелец 26.11.2026): закреплённые первыми,
    # цвет — штатное поле `color`, текст — без разметки.
    coop_pinned = fields.Boolean(string='Закреплена', index=True)
    coop_excerpt = fields.Text(string='Текст', compute='_compute_coop_excerpt')
    coop_space_label = fields.Char(string='Чья', compute='_compute_coop_space_label')

    @api.depends('description')
    def _compute_coop_excerpt(self):
        for note in self:
            # Своё, а не `html2plaintext`: тот склеивает пункты списка в строку.
            text = re.sub(r'<li[^>]*>', '\n• ', str(note.description or ''))
            text = re.sub(r'</(p|div|li|ul|ol|h[1-6])>|<br[^>]*>', '\n', text)
            text = html.unescape(re.sub(r'<[^>]+>', '', text))
            note.coop_excerpt = '\n'.join(
                line.strip() for line in text.splitlines() if line.strip())[:600]

    @api.depends(lambda self: ['coop_space', *self._coop_space_fields().values()])
    def _compute_coop_space_label(self):
        fields_by_space = self._coop_space_fields()
        for note in self:
            field = fields_by_space.get(note.coop_space)
            note.coop_space_label = (
                note[field].sudo().display_name if field else 'Личное')

    def _coop_catalog_filters(self, domain):
        """Панель «Фильтр» у заметок и задач: чьё и закреплённое."""
        return [{
            'code': 'space', 'label': 'Пространство',
            'hint': 'Личное, проект, организация или группа.',
            'widget': 'select', 'field': 'coop_space', 'operator': '=',
            'placeholder': 'Любое',
            'options': [{'value': code, 'label': label}
                        for code, label in self._fields['coop_space'].selection],
        }, {
            'code': 'pinned', 'label': 'Закреплённые',
            'hint': 'Только закреплённые заметки.',
            'widget': 'select', 'field': 'coop_pinned', 'operator': '=',
            'placeholder': 'Все',
            'options': [{'value': True, 'label': 'Закреплённые'},
                        {'value': False, 'label': 'Остальные'}],
        }]

    def action_coop_pin(self):
        for note in self:
            note.coop_pinned = not note.coop_pinned

    def action_coop_to_task(self):
        """Заметка становится задачей: текст, пространство и люди те же."""
        self.write({'coop_kind': 'task', 'coop_pinned': False})

    @api.model
    def _coop_space_fields(self):
        """Пространство → поле с его записью; модули дописывают свои."""
        return {'project': 'coop_project_id'}

    @api.model
    def _coop_team_domain(self):
        """Проекты, где человек в команде: тот же круг, что у ленты."""
        mine = self.env.user.coop_actor_partner_ids.ids
        return ['|', ('partner_id', 'in', mine),
                ('contribution_ids', 'any', [
                    ('partner_id', 'in', mine), ('state', '=', 'accepted')])]

    def _coop_space_member(self):
        """Состоит ли человек в пространстве записи."""
        self.ensure_one()
        if self.coop_space == 'project':
            domain = self._coop_team_domain()
            return bool(self.env['coop.project'].sudo().search_count(
                [('id', '=', self.coop_project_id.id)] + domain, limit=1))
        return True

    def _coop_check_space(self):
        fields_by_space = self._coop_space_fields()
        for note in self:
            field = fields_by_space.get(note.coop_space)
            if not field:
                continue
            if not note[field]:
                raise UserError(_('Укажите, чьё это пространство: «%s».',
                                  note._fields[field].string))
            if not self.env.su and not note._coop_space_member():
                raise UserError(_(
                    'Вести записи «%s» могут только участники — вы в нём не состоите.',
                    note[field].sudo().display_name))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._coop_check_space()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'coop_space' in vals or any(
                f in vals for f in self._coop_space_fields().values()):
            self._coop_check_space()
        return result


class CoopProject(models.Model):
    _inherit = 'coop.project'

    coop_note_ids = fields.Many2many(
        'project.task', string='Заметки по проекту', compute='_compute_coop_notes')
    coop_note_count = fields.Integer(
        string='Заметок', compute='_compute_coop_notes')

    def _coop_note_domain(self):
        return [('coop_project_id', 'in', self.ids),
                '|', ('user_ids', 'in', [self.env.uid]),
                ('coop_space', '=', 'project'),
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
