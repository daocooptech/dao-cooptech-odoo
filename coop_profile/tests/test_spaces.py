# -*- coding: utf-8 -*-
from odoo.addons.coop_projects.tests.common import CoopProjectCase
from odoo.exceptions import AccessError, UserError


class TestSpaces(CoopProjectCase):
    """Заметки и задачи видны по пространству (решение 696, № 353)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls._make_project()
        cls.other = cls._make_person('Посторонний Заметок')

    def _note(self, user, **vals):
        return self.env['project.task'].with_user(user).create(dict(
            name='Проверка', project_id=False, user_ids=[(6, 0, user.ids)], **vals))

    def _sees(self, user, note):
        return bool(self.env['project.task'].with_user(user).search([('id', '=', note.id)]))

    def test_personal_with_project_link_stays_private(self):
        note = self._note(self.other, coop_project_id=self.project.id)
        self.assertEqual(note.coop_space, 'personal')
        self.assertFalse(self._sees(self.initiator, note))

    def test_project_space_for_team_only(self):
        with self.assertRaises(UserError):
            self._note(self.other, coop_space='project', coop_project_id=self.project.id)
        author = self._make_person('Автор Заметок')
        note = self._note(self.initiator, coop_space='project', coop_project_id=self.project.id)
        self.assertFalse(self._sees(self.other, note))
        with self.assertRaises(AccessError):
            note.with_user(self.other).read(['name'])
        # Автор — не в команде: общая запись видна инициатору не потому,
        # что он исполнитель, а по команде проекта.
        shared = self.env['project.task'].sudo().create({
            'name': 'Общая', 'project_id': False, 'user_ids': [(6, 0, author.ids)],
            'coop_space': 'project', 'coop_project_id': self.project.id})
        self.assertTrue(self._sees(self.initiator, shared))
        shared.with_user(self.initiator).write({'name': 'Правит команда'})

    def test_space_needs_record(self):
        with self.assertRaises(UserError):
            self._note(self.initiator, coop_space='project')

    def test_community_space(self):
        group = self.env['coop.community'].create({
            'name': 'Группа проверки', 'partner_id': self.initiator.partner_id.id})
        Member = self.env['coop.community.member'].sudo()
        if not Member.search_count([('community_id', '=', group.id),
                                    ('partner_id', '=', self.initiator.partner_id.id)]):
            Member.create({'community_id': group.id,
                           'partner_id': self.initiator.partner_id.id, 'state': 'active'})
        note = self._note(self.initiator, coop_space='community', coop_community_id=group.id)
        self.assertFalse(self._sees(self.other, note))
        member = Member.create({'community_id': group.id,
                                'partner_id': self.other.partner_id.id, 'state': 'active'})
        self.assertTrue(self._sees(self.other, note))
        member.state = 'left'
        self.assertFalse(self._sees(self.other, note))
        note.coop_space = 'personal'
        self.assertFalse(note.coop_community_id)
