# -*- coding: utf-8 -*-
"""Срок сбора и правило закрытия.

До этого у проекта не было ни одной даты, и сбор не кончался никогда:
нельзя было ни показать «осталось двенадцать дней», ни закрыть сбор, ни
отличить заброшенный проект от идущего.

Проверяется здесь, потому что ошибка в правиле закрытия — это чужие
деньги, а увидеть её можно только по жалобе: снаружи недособранный
проект выглядит так же, как собранный.
"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import CoopProjectCase


@tagged('post_install', '-at_install')
class TestFundingDeadline(CoopProjectCase):

    def _open(self, project, days=30):
        project.date_deadline = fields.Date.today() + timedelta(days=days)
        project.fallback_plan = 'Запустим первую очередь без второй площадки.'
        project.action_open_gathering()
        return project

    def test_srok_stavitsya_sam_esli_ne_ukazan(self):
        project = self._make_project()
        project.fallback_plan = 'Первая очередь.'
        project.action_open_gathering()
        self.assertTrue(project.date_deadline)
        self.assertEqual(project.date_start, fields.Date.today())

    def test_slishkom_korotkiy_srok_ne_prinimaetsya(self):
        """Меньше двух недель никто не успеет узнать о проекте."""
        project = self._make_project()
        project.date_deadline = fields.Date.today() + timedelta(days=3)
        project.fallback_plan = 'Первая очередь.'
        with self.assertRaises(UserError):
            project.action_open_gathering()

    def test_slishkom_dlinnyy_srok_ne_prinimaetsya(self):
        project = self._make_project()
        project.date_deadline = fields.Date.today() + timedelta(days=400)
        project.fallback_plan = 'Первая очередь.'
        with self.assertRaises(UserError):
            project.action_open_gathering()

    def test_bez_plana_na_nepolnyy_sbor_sbor_ne_otkryt(self):
        """Вкладчик читает не про порог, а про то, что получит при нём."""
        project = self._make_project()
        # Заготовка ставит план сама — здесь его надо именно убрать.
        project.fallback_plan = False
        project.date_deadline = fields.Date.today() + timedelta(days=30)
        with self.assertRaises(ValidationError):
            project.action_open_gathering()

    def test_polnyy_sbor_plana_ne_trebuet(self):
        """Нечего обещать на неполном сборе: его не будет."""
        project = self._make_project()
        project.funding_rule = 'all_or_nothing'
        project.date_deadline = fields.Date.today() + timedelta(days=30)
        project.action_open_gathering()
        self.assertEqual(project.state, 'gathering')

    def test_porog_vne_diapazona(self):
        project = self._make_project()
        with self.assertRaises(ValidationError):
            project.funding_threshold = 20

    def test_zapusk_po_porogu_a_ne_po_stam_protsentam(self):
        project = self._make_project(required=100000)
        self._open(project)
        giver = self._make_person('Вкладчик На Порог')
        offer = self._make_offer(project, giver, value=75000)
        offer.with_user(self.initiator).action_accept()
        self.assertEqual(project.readiness, 75)
        project.action_launch()
        self.assertEqual(project.state, 'running')

    def test_nedobor_do_poroga_ne_zapuskaetsya(self):
        project = self._make_project(required=100000)
        self._open(project)
        giver = self._make_person('Недобравший Вкладчик')
        offer = self._make_offer(project, giver, value=60000)
        offer.with_user(self.initiator).action_accept()
        with self.assertRaises(UserError):
            project.action_launch()

    def test_polnyy_sbor_trebuet_sta(self):
        project = self._make_project(required=100000)
        project.funding_rule = 'all_or_nothing'
        self._open(project)
        giver = self._make_person('Вкладчик Почти Полный')
        offer = self._make_offer(project, giver, value=99000)
        offer.with_user(self.initiator).action_accept()
        with self.assertRaises(UserError):
            project.action_launch()

    def test_ostavlyaem_sobrannoe_zapuskaetsya_s_lyubym(self):
        project = self._make_project(required=100000)
        project.funding_rule = 'keep_all'
        self._open(project)
        self.assertEqual(project.readiness, 0)
        project.action_launch()
        self.assertEqual(project.state, 'running')

    # ── Закрытие по сроку ────────────────────────────────────────────────

    def test_srok_vyshel_nedobor_sbor_ne_udalsya(self):
        project = self._make_project(required=100000)
        self._open(project)
        giver = self._make_person('Вкладчик Просроченного')
        offer = self._make_offer(project, giver, value=30000)
        offer.with_user(self.initiator).action_accept()
        need = self._make_need(project)

        project.date_deadline = fields.Date.today() - timedelta(days=1)
        self.Project.close_expired_gatherings()

        self.assertEqual(project.state, 'failed')
        self.assertEqual(need.state, 'closed', 'объявления не сняты')

    def test_srok_vyshel_sobrano_zapuskaetsya(self):
        project = self._make_project(required=100000)
        self._open(project)
        giver = self._make_person('Вкладчик Собравшего')
        offer = self._make_offer(project, giver, value=80000)
        offer.with_user(self.initiator).action_accept()

        project.date_deadline = fields.Date.today() - timedelta(days=1)
        self.Project.close_expired_gatherings()

        self.assertEqual(project.state, 'running')

    def test_srok_ne_vyshel_ne_trogaem(self):
        project = self._make_project(required=100000)
        self._open(project, days=30)
        self.Project.close_expired_gatherings()
        self.assertEqual(project.state, 'gathering')

    def test_ne_udalsya_eto_ne_otmena(self):
        """За отмену отвечает человек, за несостоявшийся сбор — никто."""
        project = self._make_project(required=100000)
        self._open(project)
        project.action_fail()
        self.assertEqual(project.state, 'failed')

    def test_priznat_nesostoyavshimsya_mozhno_tolko_v_sbore(self):
        project = self._make_project(state='running')
        with self.assertRaises(UserError):
            project.action_fail()

    def test_investitsionnyy_sbor_zakryt_bez_statusa_operatora(self):
        """Заём и доля через платформу требуют статуса оператора."""
        project = self._make_project()
        project.contribution_basis = 'investment'
        project.fallback_plan = 'Первая очередь.'
        with self.assertRaises(UserError):
            project.action_open_gathering()

    def test_so_statusom_operatora_investitsii_otkryvayutsya(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'coop.investment_operator', 'True')
        project = self._make_project()
        project.contribution_basis = 'investment'
        project.fallback_plan = 'Первая очередь.'
        project.action_open_gathering()
        self.assertEqual(project.state, 'gathering')

    def test_ostalos_dney_schitaetsya_tolko_v_sbore(self):
        project = self._make_project(required=100000)
        self._open(project, days=20)
        self.assertEqual(project.days_left, 20)
        project.action_cancel()
        self.assertEqual(project.days_left, 0)
