# -*- coding: utf-8 -*-
"""Кто видит проект в управлении.

В Odoo 20 видимость «followers» — это команда проекта, а не подписчики.
Пока доступ считали подпиской, настоящий проект видел один инициатор, а
исполнители видели задачи без проекта (разбор ux 08.10.2026, решение 452).
"""
from odoo.tests import tagged

from .common import CoopProjectCase


@tagged('post_install', '-at_install')
class TestProjectTeam(CoopProjectCase):

    def _launched(self, *givers):
        project = self._make_project(required=100000, state='gathering')
        share = 100000 // len(givers)
        for giver in givers:
            self._make_offer(project, giver, value=share).with_user(
                self.initiator).action_accept()
        project.action_launch()
        return project

    def _sees(self, user, managed):
        return bool(self.env['project.project'].with_user(user).search(
            [('id', '=', managed.id)]))

    def test_vkladchik_vidit_proekt_bez_zadach(self):
        giver = self._make_person('Вкладчик Без Задач')
        stranger = self._make_person('Посторонний Участник')
        managed = self._launched(giver).project_id
        self.assertTrue(self._sees(self.initiator, managed))
        self.assertTrue(self._sees(giver, managed))
        self.assertFalse(self._sees(stranger, managed))

    def test_ispolnitel_zadachi_vhodit_v_komandu(self):
        giver = self._make_person('Вкладчик Для Задачи')
        worker = self._make_person('Исполнитель Задачи')
        managed = self._launched(giver).project_id
        self.assertFalse(self._sees(worker, managed))
        self.env['project.task'].create({
            'name': 'Залить фундамент',
            'project_id': managed.id,
            'user_ids': [(4, worker.id)],
        })
        self.assertTrue(self._sees(worker, managed))

    def test_prinyatyy_posle_zapuska_vhodit_srazu(self):
        first = self._make_person('Первый Вкладчик')
        late = self._make_person('Поздний Вкладчик')
        project = self._launched(first)
        offer = self._make_offer(project, late, value=10000)
        self.assertFalse(self._sees(late, project.project_id))
        offer.with_user(self.initiator).action_accept()
        self.assertTrue(self._sees(late, project.project_id))

    def test_za_organizaciyu_vidyat_eyo_predstaviteli(self):
        org = self._make_org('ООО Вклад Техникой')
        agent = self._make_person('Представитель По Сделкам')
        reader = self._make_person('Член Без Полномочий')
        self._join(agent, org, powers=('deal',))
        self._join(reader, org)
        managed = self._launched(org).project_id
        self.assertTrue(self._sees(agent, managed))
        self.assertFalse(self._sees(reader, managed))

    def test_dobor_komandy_u_staryh_proektov(self):
        giver = self._make_person('Вкладчик Старого Проекта')
        project = self._launched(giver)
        managed = project.project_id
        # Как было до правки: в команде один инициатор.
        managed.allowed_internal_user_ids = [(6, 0, self.initiator.ids)]
        self.assertFalse(self._sees(giver, managed))
        self.Project.backfill_managed_projects()
        self.assertTrue(self._sees(giver, managed))
