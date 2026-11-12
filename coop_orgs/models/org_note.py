# -*- coding: utf-8 -*-
"""Заметки организации — общие для действующего состава (решение 655,
задача 428).

Та же штатная заметка To-Do (`project.task` без проекта движка), что у
людей и проектов (задача 426), но с привязкой к организации. Видят и
правят её все, кто сейчас состоит в организации: правило доступа
смотрит на действующее членство, а не на список исполнителей, поэтому
новый участник сразу видит заметки, а вышедший — перестаёт.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    coop_org_id = fields.Many2one(
        'res.partner', string='Организация', index='btree_not_null',
        ondelete='set null', domain=[('is_company', '=', True)],
        help='Заметку видит весь действующий состав организации.')
    # Срок To-Do — дата со временем; на плитке время лишнее («5 дек., 03:00»).
    coop_deadline_day = fields.Date(
        string='Срок', compute='_compute_coop_deadline_day')

    @api.depends('date_deadline')
    @api.depends_context('tz')
    def _compute_coop_deadline_day(self):
        for note in self:
            note.coop_deadline_day = note.date_deadline and fields.Datetime.context_timestamp(
                note, note.date_deadline).date()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._coop_check_org_member()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'coop_org_id' in vals:
            self._coop_check_org_member()
        return result

    def _coop_check_org_member(self):
        """Привязать заметку можно только к организации, где состоишь."""
        if self.env.su:
            return
        me = self.env.user.partner_id
        for note in self.filtered('coop_org_id'):
            if not note.coop_org_id.sudo().coop_member_ids.filtered(
                    lambda m: m.partner_id == me and m.state == 'active'):
                raise UserError(_(
                    'Заметку организации «%s» могут вести только те, кто в ней '
                    'состоит.') % note.coop_org_id.name)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_org_note_ids = fields.Many2many(
        'project.task', string='Заметки организации',
        compute='_compute_coop_org_notes')
    coop_org_note_count = fields.Integer(
        string='Заметок организации', compute='_compute_coop_org_notes')

    def _coop_org_note_domain(self):
        return [('coop_org_id', 'in', self.ids), ('project_id', '=', False),
                ('parent_id', '=', False)]

    @api.depends_context('uid')
    @api.depends('coop_member_ids.state')
    def _compute_coop_org_notes(self):
        Task = self.env['project.task']
        ids = [r.id for r in self if isinstance(r.id, int) and r.is_company]
        # Своими правами: правило доступа само отрежет чужие организации.
        notes = Task.search(self.browse(ids)._coop_org_note_domain(),
                            order='state, date_deadline, write_date desc') if ids else Task
        for record in self:
            mine = notes.filtered(lambda n: n.coop_org_id.id == record.id)
            record.coop_org_note_ids = mine[:12]
            record.coop_org_note_count = len(mine)

    def action_coop_org_notes(self):
        """Все заметки организации — список To-Do с отбором по ней."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'coop_projects.action_coop_notes')
        action['name'] = _('Заметки: %s') % self.name
        action['domain'] = self._coop_org_note_domain()
        action['context'] = dict(
            self.env.context, default_coop_org_id=self.id,
            default_project_id=False, search_default_open_tasks=1,
            list_view_ref='project_todo.project_task_view_todo_tree',
            show_task_options=False)
        action['help'] = _(
            '<p class="o_view_nocontent_smiling_face">Заметок организации пока нет</p>'
            '<p>Их видит и ведёт весь действующий состав «%s».</p>') % self.name
        return action

    def action_coop_org_new_note(self):
        """Новая заметка организации — сразу формой To-Do."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Новая заметка'),
            'res_model': 'project.task',
            'view_mode': 'form',
            'views': [(self.env.ref('project_todo.project_task_view_todo_form').id, 'form')],
            'target': 'current',
            'context': {'default_coop_org_id': self.id, 'default_project_id': False,
                        'default_user_ids': [(6, 0, [self.env.uid])]},
        }
