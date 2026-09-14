# -*- coding: utf-8 -*-
"""Состояния проекта и что происходит при переходах.

Главное здесь — заморозка и отмена: объявления снимаются с публикации в
`write`, а не в кнопке, потому что состояние меняют и загрузчиком, и
переносом, и правкой из списка. Такая проверка ничего не показывает
снаружи: если снятие отвалится, каталог просто продолжит звать людей в
остановленный проект.
"""
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import CoopProjectCase


@tagged('post_install', '-at_install')
class TestProjectLifecycle(CoopProjectCase):

    def test_novyy_proekt_zamysel(self):
        project = self._make_project()
        self.assertEqual(project.state, 'draft')
        self.assertEqual(project.readiness, 0)

    def test_sbor_bez_summy_ne_otkryt(self):
        """Без «нужно» готовность считать не от чего."""
        project = self._make_project(required=0)
        with self.assertRaises(UserError):
            project.action_open_gathering()

    def test_sbor_trebuet_podtverzhdyonnoy_lichnosti(self):
        stranger = self._make_person('Неподтверждённый Затейник')
        project = self._make_project(partner=stranger.partner_id)
        with self.assertRaises(UserError):
            project.action_open_gathering()

    def test_zapusk_tolko_sobrannogo(self):
        project = self._make_project(state='gathering')
        self.assertEqual(project.readiness, 0)
        with self.assertRaises(UserError):
            project.action_launch()

    def test_gotovnost_schitaetsya_ot_prinyatyh(self):
        """Предложенный вклад в готовность не идёт: он ещё не вклад."""
        project = self._make_project(required=100000)
        giver = self._make_person('Щедрый Вкладчик')
        offer = self._make_offer(project, giver, value=40000)
        self.assertEqual(project.readiness, 0)
        offer.with_user(self.initiator).action_accept()
        self.assertEqual(project.contribution_total, 40000)
        self.assertEqual(project.readiness, 40)
        self.assertEqual(project.contributor_count, 1)

    def test_dolya_skladyvaetsya_a_ne_vpisyvaetsya(self):
        project = self._make_project(required=100000)
        first = self._make_person('Первый Вкладчик')
        second = self._make_person('Второй Вкладчик')
        one = self._make_offer(project, first, value=30000)
        two = self._make_offer(project, second, value=10000)
        one.with_user(self.initiator).action_accept()
        two.with_user(self.initiator).action_accept()
        self.assertEqual(one.share_percent, 75)
        self.assertEqual(two.share_percent, 25)

    # ── Заморозка ────────────────────────────────────────────────────────

    def test_zamorozka_pomnit_kuda_vernutsya(self):
        project = self._make_project(state='gathering')
        project.action_freeze()
        self.assertEqual(project.state, 'frozen')
        self.assertEqual(project.resume_state, 'gathering')
        project.action_resume()
        self.assertEqual(project.state, 'gathering')
        self.assertFalse(project.resume_state)

    def test_zapushchennyy_vozvrashchaetsya_zapushchennym(self):
        project = self._make_project(state='running')
        project.action_freeze()
        self.assertEqual(project.resume_state, 'running')
        project.action_resume()
        self.assertEqual(project.state, 'running')

    def test_zamysel_zamorozit_nelzya(self):
        project = self._make_project()
        with self.assertRaises(UserError):
            project.action_freeze()

    def test_razmorozit_nezamorozhennoe_nelzya(self):
        project = self._make_project(state='gathering')
        with self.assertRaises(UserError):
            project.action_resume()

    def test_zamorozka_snimaet_obyavleniya(self):
        project = self._make_project(state='gathering')
        need = self._make_need(project)
        self.assertEqual(need.state, 'published')
        project.action_freeze()
        self.assertEqual(need.state, 'closed')

    def test_otmena_snimaet_obyavleniya(self):
        project = self._make_project(state='gathering')
        need = self._make_need(project)
        project.action_cancel()
        self.assertEqual(project.state, 'cancelled')
        self.assertEqual(need.state, 'closed')

    def test_obyavleniya_snimayutsya_i_pri_pravke_sostoyaniya(self):
        """Не в кнопке, а в `write`: состояние меняют и загрузчиком тоже."""
        project = self._make_project(state='gathering')
        need = self._make_need(project)
        project.write({'state': 'cancelled'})
        self.assertEqual(need.state, 'closed')

    def test_razmorozka_ne_podnimaet_obyavleniya_obratno(self):
        """Намеренно: пока проект стоял, часть потребностей отпала."""
        project = self._make_project(state='gathering')
        need = self._make_need(project)
        project.action_freeze()
        project.action_resume()
        self.assertEqual(need.state, 'closed')

    def test_zavershenie_obyavleniya_ne_trogaet(self):
        """Завершённый проект — не остановленный: он доведён до конца."""
        project = self._make_project(state='running')
        need = self._make_need(project)
        project.action_finish()
        self.assertEqual(project.state, 'done')
        self.assertEqual(need.state, 'published')
