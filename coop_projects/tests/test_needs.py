# -*- coding: utf-8 -*-
"""Потребность проекта и утверждение одного предложения.

Порядок фрилансовый, как просил владелец: на потребность приходят
предложения, ответственный смотрит все и утверждает одно, остальные
отклоняются в тот же момент. Здесь проверяется именно «в тот же
момент»: если отклонение отвалится, откликнувшиеся так и останутся
висеть в ожидании, и никакой ошибки об этом не скажет.
"""
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import CoopProjectCase


@tagged('post_install', '-at_install')
class TestProjectNeeds(CoopProjectCase):

    def test_potrebnost_eto_spros(self):
        """Потребность проекта — объявление спроса, не предложения."""
        project = self._make_project()
        with self.assertRaises(ValidationError):
            self.Resource.create({
                'name': 'Продам лишнее',
                'listing_type': 'offer',
                'project_id': project.id,
                'owner_id': project.partner_id.id,
            })

    def test_potrebnost_vidna_kak_proektnaya(self):
        project = self._make_project(state='gathering')
        need = self._make_need(project)
        self.assertTrue(need.is_project_need)
        chastnoe = self.Resource.create({
            'name': 'Ищу сварщика для себя',
            'listing_type': 'request',
            'owner_id': self.initiator.partner_id.id,
        })
        self.assertFalse(chastnoe.is_project_need)

    def test_schyot_predlozheniy_tolko_nerassmotrennye(self):
        project = self._make_project(state='gathering')
        need = self._make_need(project)
        first = self._make_person('Откликнувшийся Первым')
        second = self._make_person('Откликнувшийся Вторым')
        self._make_offer(project, first, need=need)
        self._make_offer(project, second, need=need)
        self.assertEqual(need.need_offer_count, 2)

    def test_utverzhdenie_zakryvaet_potrebnost(self):
        project = self._make_project(state='gathering')
        need = self._make_need(project)
        chosen_by = self._make_person('Выбранный Исполнитель')
        chosen = self._make_offer(project, chosen_by, need=need)
        chosen.with_user(self.initiator).action_accept()
        self.assertEqual(chosen.state, 'accepted')
        self.assertEqual(need.state, 'closed')
        self.assertEqual(need.need_accepted_id, chosen)

    def test_ostalnye_otklonyayutsya_srazu(self):
        """Держать людей в ожидании после выбора — неуважение к их времени."""
        project = self._make_project(state='gathering')
        need = self._make_need(project)
        winner = self._make_person('Победивший Исполнитель')
        loser_one = self._make_person('Непрошедший Первый')
        loser_two = self._make_person('Непрошедший Второй')
        chosen = self._make_offer(project, winner, need=need)
        others = (self._make_offer(project, loser_one, need=need)
                  | self._make_offer(project, loser_two, need=need))
        chosen.with_user(self.initiator).action_accept()
        self.assertEqual(set(others.mapped('state')), {'declined'})
        self.assertEqual(need.need_offer_count, 0)

    def test_predlozheniya_chuzhoy_potrebnosti_ne_trogayut(self):
        project = self._make_project(state='gathering')
        one = self._make_need(project, name='Нужны доски')
        two = self._make_need(project, name='Нужен бетон')
        winner = self._make_person('Исполнитель По Доскам')
        bystander = self._make_person('Исполнитель По Бетону')
        chosen = self._make_offer(project, winner, need=one)
        untouched = self._make_offer(project, bystander, need=two)
        chosen.with_user(self.initiator).action_accept()
        self.assertEqual(untouched.state, 'offered')
        self.assertEqual(two.state, 'published')

    def test_utverzhdaet_initsiator(self):
        """Вклад, принятый вкладчиком самому себе, размывал бы доли."""
        project = self._make_project(state='gathering')
        need = self._make_need(project)
        giver = self._make_person('Самоназначенный Вкладчик')
        offer = self._make_offer(project, giver, need=need)
        with self.assertRaises(UserError):
            offer.with_user(giver).action_accept()

    def test_utverzhdaet_i_otvetstvennyy_za_potrebnost(self):
        """На проекте в три десятка нужд инициатор — узкое место."""
        project = self._make_project(state='gathering')
        manager = self._make_person('Ответственный За Потребность')
        need = self._make_need(project, manager=manager.partner_id)
        giver = self._make_person('Откликнувшийся На Нужду')
        offer = self._make_offer(project, giver, need=need)
        offer.with_user(manager).action_accept()
        self.assertEqual(offer.state, 'accepted')
        self.assertEqual(need.state, 'closed')

    def test_otvetstvennyy_chuzhoy_potrebnosti_ne_utverzhdaet(self):
        project = self._make_project(state='gathering')
        manager = self._make_person('Ответственный За Доски')
        self._make_need(project, name='Нужны доски', manager=manager.partner_id)
        other_need = self._make_need(project, name='Нужен бетон')
        giver = self._make_person('Откликнувшийся На Бетон')
        offer = self._make_offer(project, giver, need=other_need)
        with self.assertRaises(UserError):
            offer.with_user(manager).action_accept()

    def test_vklad_bez_potrebnosti_prinimaetsya_kak_ran_she(self):
        """Деньги «просто в проект» вносят и без объявленной нужды."""
        project = self._make_project(state='gathering')
        giver = self._make_person('Денежный Вкладчик')
        offer = self._make_offer(project, giver, value=25000)
        offer.with_user(self.initiator).action_accept()
        self.assertEqual(offer.state, 'accepted')

    def test_predstavitel_organizatsii_utverzhdaet_po_polnomochiyu(self):
        """У организации кнопку нажимает человек, которому поручены сделки."""
        org = self._make_org('ПК «Проектный»')
        self._confirm(org, 'registry', method='registry')
        agent = self._make_person('Уполномоченный По Сделкам')
        self._join(agent, org, powers=('deal',))
        project = self._make_project(partner=org, state='gathering')
        need = self._make_need(project)
        giver = self._make_person('Откликнувшийся В Организацию')
        offer = self._make_offer(project, giver, need=need)
        offer.with_user(agent).action_accept()
        self.assertEqual(offer.state, 'accepted')
