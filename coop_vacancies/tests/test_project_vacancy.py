# -*- coding: utf-8 -*-
"""Вакансия проекта: утверждённый отклик становится вкладом.

Решение владельца от 14 сентября 2026: работа проекта размещается в
вакансиях, а не в ресурсах, и отклик на такую вакансию — то же, что
предложение на потребность. У вакансии организации ничего этого не
происходит: там наём, а не складчина, и доли не возникает. Разницу
между двумя случаями легко потерять при первой же правке приглашения —
и снаружи это не видно: вакансия закроется, а вклад не появится.
"""
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.coop_projects.tests.common import CoopProjectCase


@tagged('post_install', '-at_install')
class TestProjectVacancy(CoopProjectCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Vacancy = cls.env['coop.vacancy']
        cls.Application = cls.env['coop.vacancy.application']

    @classmethod
    def _make_vacancy(cls, project=None, partner=None, value=60000,
                      manager=None):
        return cls.Vacancy.create({
            'name': 'Нужен сварщик',
            'coop_project_id': project.id if project else False,
            'partner_id': (partner or (project and project.partner_id)
                           or cls.initiator.partner_id).id,
            'need_manager_id': manager.id if manager else False,
            'contribution_value': value,
            'reward_kind': 'share',
            'state': 'published',
        })

    @classmethod
    def _apply(cls, vacancy, who):
        return cls.Application.create({
            'vacancy_id': vacancy.id,
            'partner_id': who.partner_id.id,
            'state': 'applied',
        })

    def test_utverzhdyonnyy_otklik_stanovitsya_vkladom(self):
        project = self._make_project(state='gathering', required=100000)
        vacancy = self._make_vacancy(project)
        worker = self._make_person('Утверждённый Сварщик')
        application = self._apply(vacancy, worker)

        application.with_user(self.initiator).action_invite()

        self.assertEqual(application.state, 'invited')
        contribution = application.contribution_id
        self.assertTrue(contribution, 'вклад по отклику не завёлся')
        self.assertEqual(contribution.kind, 'labour')
        self.assertEqual(contribution.state, 'accepted')
        self.assertEqual(contribution.value, 60000)
        self.assertEqual(contribution.partner_id, worker.partner_id)
        self.assertEqual(project.contribution_total, 60000)
        self.assertEqual(project.readiness, 60)

    def test_vakansiya_zakryvaetsya_ostalnye_otklonyayutsya(self):
        project = self._make_project(state='gathering')
        vacancy = self._make_vacancy(project)
        winner = self._make_person('Победивший Сварщик')
        loser = self._make_person('Непрошедший Сварщик')
        chosen = self._apply(vacancy, winner)
        other = self._apply(vacancy, loser)

        chosen.with_user(self.initiator).action_invite()

        self.assertEqual(vacancy.state, 'closed')
        self.assertEqual(other.state, 'declined')
        self.assertEqual(vacancy.need_accepted_id, chosen.contribution_id)

    def test_otvetstvennyy_za_potrebnost_utverzhdaet(self):
        project = self._make_project(state='gathering')
        manager = self._make_person('Ответственный За Работу')
        vacancy = self._make_vacancy(project, manager=manager.partner_id)
        worker = self._make_person('Откликнувшийся Сварщик')
        application = self._apply(vacancy, worker)

        application.with_user(manager).action_invite()

        self.assertTrue(application.contribution_id)

    def test_otklikayushchiysya_sam_sebya_ne_utverzhdaet(self):
        project = self._make_project(state='gathering')
        vacancy = self._make_vacancy(project)
        worker = self._make_person('Самоназначенный Сварщик')
        application = self._apply(vacancy, worker)
        with self.assertRaises(UserError):
            application.with_user(worker).action_invite()

    def test_vakansiya_organizatsii_vklada_ne_rozhdaet(self):
        """Там наём, а не складчина: доли не возникает."""
        org = self._make_org('ООО «Нанимающее»')
        employer = self._make_person('Кадровик Организации')
        self._join(employer, org, powers=('publish',))
        vacancy = self._make_vacancy(project=None, partner=org)
        worker = self._make_person('Нанимаемый Сварщик')
        application = self._apply(vacancy, worker)

        application.with_user(employer).action_invite()

        self.assertEqual(application.state, 'invited')
        self.assertFalse(application.contribution_id)
        self.assertNotEqual(vacancy.state, 'closed')

    def test_volontyorskaya_vakansiya_dayot_vklad_v_nol(self):
        """Ноль — это правда, а не недосмотр: волонтёрство доли не даёт."""
        project = self._make_project(state='gathering')
        vacancy = self._make_vacancy(project, value=0)
        vacancy.reward_kind = 'volunteer'
        worker = self._make_person('Волонтёр На Стройке')
        application = self._apply(vacancy, worker)

        application.with_user(self.initiator).action_invite()

        self.assertTrue(application.contribution_id)
        self.assertEqual(application.contribution_id.value, 0)

    def test_upravlyaemyy_proekt_podstavlyaetsya_sam(self):
        """Вводить его заново — способ получить вакансию не в том проекте."""
        project = self._make_project(state='gathering')
        project.project_id = self.env['project.project'].create(
            {'name': 'Управляемый для проверки'}).id
        vacancy = self._make_vacancy(project)
        self.assertEqual(vacancy.project_id, project.project_id)
