# -*- coding: utf-8 -*-
"""Этапы ведения — отдельно от состояния сбора.

«Идея → Сбор → Запущен → Завершён» это автомат сбора: один на всю
платформу, меняется кодом, описан законом и решениями владельца. Этапы
ведения — столбцы канбана, которые кооператив правит сам под своё дело.

Смешать их легко, и снаружи это не видно: пока проектов в управлении
мало, оба поля выглядят одинаково осмысленно.
"""
from odoo.tests import tagged

from .common import CoopProjectCase


@tagged('post_install', '-at_install')
class TestProjectStages(CoopProjectCase):

    def _stage(self, key):
        return self.env.ref('coop_projects.project_stage_%s' % key,
                            raise_if_not_found=False)

    def test_nabor_etapov_zavedyon(self):
        for key in ('preparation', 'supply', 'work', 'acceptance',
                    'settlement', 'stopped'):
            self.assertTrue(self._stage(key), 'нет этапа %s' % key)

    def test_itogi_i_ostanovka_svyornuty(self):
        """В канбане это архив, а не работа."""
        self.assertTrue(self._stage('settlement').fold)
        self.assertTrue(self._stage('stopped').fold)
        self.assertFalse(self._stage('work').fold)

    def test_shtatnye_etapy_ubrany_v_arhiv(self):
        """Не удалены: записи чужого модуля с защитой от обновления."""
        old = self.env.ref('project.project_project_stage_0',
                           raise_if_not_found=False)
        if not old:
            self.skipTest('Штатных этапов на узле нет')
        self.assertFalse(old.active)

    def test_zapushchennyy_proekt_nachinaetsya_s_podgotovki(self):
        project = self._make_project(required=100000)
        project.date_deadline = self.env['ir.fields.converter'] and False
        project.write({'state': 'gathering'})
        giver = self._make_person('Вкладчик Для Запуска')
        offer = self._make_offer(project, giver, value=100000)
        offer.with_user(self.initiator).action_accept()
        project.action_launch()

        self.assertTrue(project.project_id)
        self.assertEqual(project.project_id.stage_id, self._stage('preparation'))
        # Этап виден на карточке сбора, но живёт в управлении проектами.
        self.assertEqual(project.project_stage_id, self._stage('preparation'))

    def test_sostoyanie_sbora_ot_etapa_ne_zavisit(self):
        """Две разные корзины: собрали ли и где идут работы."""
        project = self._make_project(required=100000)
        project.write({'state': 'gathering'})
        giver = self._make_person('Вкладчик Двух Корзин')
        offer = self._make_offer(project, giver, value=100000)
        offer.with_user(self.initiator).action_accept()
        project.action_launch()

        project.project_id.stage_id = self._stage('work')
        self.assertEqual(project.state, 'running')
        project.action_finish()
        self.assertEqual(project.state, 'done')
        # Завершение сбора этап ведения не трогает: работы закрывает тот,
        # кто их ведёт, а не тот, кто закрыл сбор.
        self.assertEqual(project.project_id.stage_id, self._stage('work'))
