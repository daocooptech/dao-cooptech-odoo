# -*- coding: utf-8 -*-
"""Возврат вклада.

Два принципа, из которых выводится всё остальное: возвращается то, что
ещё не потрачено; и участник не может оказаться должен проекту —
максимум, чем он рискует, это его вклад. За этой границей кооперация
превращается в кабалу.

Проверяется здесь, потому что ошибка тут — чужие деньги, а увидеть её
можно только по жалобе того, кому не вернули.
"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import CoopProjectCase


@tagged('post_install', '-at_install')
class TestContributionRefund(CoopProjectCase):

    def _gathering(self, required=100000):
        project = self._make_project(required=required)
        project.date_deadline = fields.Date.today() + timedelta(days=30)
        project.action_open_gathering()
        return project

    # ── Период отзыва ────────────────────────────────────────────────────

    def test_nepriniatyy_vklad_otzyvaetsya_svobodno(self):
        """Проект на него ещё не рассчитывал."""
        project = self._gathering()
        giver = self._make_person('Передумавший Вкладчик')
        offer = self._make_offer(project, giver, value=20000)
        self.assertTrue(offer.can_withdraw)
        offer.with_user(giver).action_withdraw()
        self.assertEqual(offer.state, 'withdrawn')

    def test_prinyatyy_vklad_otzyvaetsya_v_period(self):
        project = self._gathering()
        giver = self._make_person('Отзывающий Вкладчик')
        offer = self._make_offer(project, giver, value=20000)
        offer.with_user(self.initiator).action_accept()
        self.assertEqual(offer.withdraw_until,
                         fields.Date.today() + timedelta(days=7))
        offer.with_user(giver).action_withdraw()
        self.assertEqual(offer.state, 'withdrawn')

    def test_posle_perioda_otozvat_nelzya(self):
        project = self._gathering()
        giver = self._make_person('Опоздавший Вкладчик')
        offer = self._make_offer(project, giver, value=20000)
        offer.with_user(self.initiator).action_accept()
        offer.accepted_on = fields.Date.today() - timedelta(days=30)
        offer.invalidate_recordset()
        self.assertFalse(offer.can_withdraw)
        with self.assertRaises(UserError):
            offer.with_user(giver).action_withdraw()

    def test_okno_ne_dlinnee_sroka_sbora(self):
        """Сбор закрылся — отзывать уже нечего."""
        project = self._gathering()
        project.date_deadline = fields.Date.today() + timedelta(days=2)
        giver = self._make_person('Вкладчик Перед Закрытием')
        offer = self._make_offer(project, giver, value=20000)
        offer.with_user(self.initiator).action_accept()
        self.assertEqual(offer.withdraw_until,
                         fields.Date.today() + timedelta(days=2))

    def test_otozvat_chuzhoy_vklad_nelzya(self):
        project = self._gathering()
        giver = self._make_person('Чей-то Вкладчик')
        offer = self._make_offer(project, giver, value=20000)
        with self.assertRaises(UserError):
            offer.with_user(self.initiator).action_withdraw()

    # ── Передача по акту ─────────────────────────────────────────────────

    def test_peredat_do_zapuska_nelzya(self):
        """Пока сбор не закрыт, передача только мешает вернуть вклад."""
        project = self._gathering()
        giver = self._make_person('Ранний Поставщик')
        offer = self._make_offer(project, giver, value=20000)
        offer.with_user(self.initiator).action_accept()
        with self.assertRaises(UserError):
            offer.action_mark_delivered()

    def test_peredannoe_ne_otzyvaetsya(self):
        project = self._gathering()
        giver = self._make_person('Поставщик Материалов')
        offer = self._make_offer(project, giver, value=100000)
        offer.with_user(self.initiator).action_accept()
        project.action_launch()
        offer.action_mark_delivered()
        offer.invalidate_recordset()
        self.assertFalse(offer.can_withdraw)

    # ── Провал сбора ─────────────────────────────────────────────────────

    def test_proval_vozvrashchaet_dengi_i_snimaet_obeshchannoe(self):
        project = self._gathering(required=200000)
        payer = self._make_person('Денежный Вкладчик Провала')
        worker = self._make_person('Трудовой Вкладчик Провала')
        outsider = self._make_person('Непринятый Вкладчик')

        money = self.Contribution.create({
            'project_id': project.id, 'partner_id': payer.partner_id.id,
            'kind': 'money', 'name': 'Взнос', 'value': 30000,
            'state': 'offered'})
        labour = self.Contribution.create({
            'project_id': project.id, 'partner_id': worker.partner_id.id,
            'kind': 'labour', 'name': 'Смены', 'value': 20000,
            'state': 'offered'})
        pending = self._make_offer(project, outsider, value=10000)
        money.with_user(self.initiator).action_accept()
        labour.with_user(self.initiator).action_accept()

        project.action_fail()

        self.assertEqual(money.state, 'returned')
        self.assertEqual(money.refund_amount, 30000)
        # Смена экскаваторщика не передавалась, а была обещана. Снимается
        # именно обещание.
        self.assertEqual(labour.state, 'released')
        # Никто его не отклонял — просто вышел срок.
        self.assertEqual(pending.state, 'expired')

    def test_otmena_zapuskaet_tot_zhe_raschyot(self):
        project = self._gathering()
        payer = self._make_person('Вкладчик Отменённого')
        money = self.Contribution.create({
            'project_id': project.id, 'partner_id': payer.partner_id.id,
            'kind': 'money', 'name': 'Взнос', 'value': 15000,
            'state': 'offered'})
        money.with_user(self.initiator).action_accept()
        project.action_cancel()
        # Отмена снимает объявления, но расчёт по очередям — отдельное
        # действие: распределение чужих денег должно быть видно до
        # нажатия, а не случиться молча.
        self.assertEqual(project.state, 'cancelled')

    # ── Израсходованное и возмещение ─────────────────────────────────────

    def test_izraskhodovannoe_vozmeshchaetsya_dengami(self):
        """Вернуть в натуре нельзя — возмещается действительная стоимость."""
        project = self._gathering()
        giver = self._make_person('Поставщик Израсходованного')
        offer = self._make_offer(project, giver, value=50000)
        offer.with_user(self.initiator).action_accept()
        offer.action_consume()
        self.assertEqual(offer.state, 'consumed')
        offer.action_compensate(amount=30000)
        self.assertEqual(offer.state, 'compensated')
        self.assertEqual(offer.refund_amount, 30000)
        # Не долг проекта, а признанная потеря участника.
        self.assertEqual(offer.unrecovered_amount, 20000)

    def test_trud_vozvrashchaetsya_dengami_a_ne_v_nature(self):
        project = self._gathering()
        worker = self._make_person('Работавший Участник')
        labour = self.Contribution.create({
            'project_id': project.id, 'partner_id': worker.partner_id.id,
            'kind': 'labour', 'name': 'Сварка', 'value': 40000,
            'state': 'offered'})
        self.assertEqual(labour.return_mode, 'compensation')

    def test_dengi_vozvrashchayutsya_dengami(self):
        project = self._gathering()
        payer = self._make_person('Денежный Участник')
        money = self.Contribution.create({
            'project_id': project.id, 'partner_id': payer.partner_id.id,
            'kind': 'money', 'name': 'Взнос', 'value': 10000,
            'state': 'offered'})
        self.assertEqual(money.return_mode, 'money_back')

    def test_tekhnika_vozvrashchaetsya_v_nature(self):
        project = self._gathering()
        giver = self._make_person('Владелец Техники')
        thing = self.Contribution.create({
            'project_id': project.id, 'partner_id': giver.partner_id.id,
            'kind': 'resource', 'name': 'Экскаватор', 'value': 300000,
            'state': 'offered'})
        self.assertEqual(thing.return_mode, 'in_kind')

    def test_ostavit_proektu_mozhet_tolko_vkladchik(self):
        """Молчание согласием не считается, и решить за человека нельзя."""
        project = self._gathering()
        giver = self._make_person('Щедрый Участник')
        offer = self._make_offer(project, giver, value=20000)
        offer.with_user(self.initiator).action_accept()
        with self.assertRaises(UserError):
            offer.with_user(self.initiator).action_waive()
        offer.with_user(giver).action_waive()
        self.assertEqual(offer.state, 'waived')

    # ── Паевой взнос и членство ──────────────────────────────────────────

    def test_pay_vnosit_tolko_payshchik(self):
        """Вкладчик-непайщик превращает пай в привлечение со стороны."""
        org = self._make_org('ПК «Паевой»')
        self._confirm(org, 'registry', method='registry')
        agent = self._make_person('Председатель Паевого')
        self._join(agent, org, powers=('deal',))
        project = self._make_project(partner=org, required=100000)
        project.contribution_basis = 'share'
        project.date_deadline = fields.Date.today() + timedelta(days=30)
        project.action_open_gathering()

        stranger = self._make_person('Посторонний Вкладчик')
        money = self.Contribution.create({
            'project_id': project.id, 'partner_id': stranger.partner_id.id,
            'kind': 'money', 'name': 'Взнос', 'value': 20000,
            'state': 'offered'})
        with self.assertRaises(ValidationError):
            money.with_user(agent).action_accept()

    def test_payshchik_vnosit_pay_svobodno(self):
        org = self._make_org('ПК «Пайщиков»')
        self._confirm(org, 'registry', method='registry')
        agent = self._make_person('Председатель Пайщиков')
        self._join(agent, org, powers=('deal',))
        payer = self._make_person('Настоящий Пайщик')
        self._join(payer, org)
        project = self._make_project(partner=org, required=100000)
        project.contribution_basis = 'share'
        project.date_deadline = fields.Date.today() + timedelta(days=30)
        project.action_open_gathering()

        money = self.Contribution.create({
            'project_id': project.id, 'partner_id': payer.partner_id.id,
            'kind': 'money', 'name': 'Паевой взнос', 'value': 20000,
            'state': 'offered'})
        money.with_user(agent).action_accept()
        self.assertEqual(money.state, 'accepted')

    def test_trud_v_paevoy_proekt_nesyot_kto_ugodno(self):
        """Труд в предмет закона об инвестплатформах не попадает."""
        org = self._make_org('ПК «Трудовой»')
        self._confirm(org, 'registry', method='registry')
        agent = self._make_person('Председатель Трудового')
        self._join(agent, org, powers=('deal',))
        project = self._make_project(partner=org, required=100000)
        project.contribution_basis = 'share'
        project.date_deadline = fields.Date.today() + timedelta(days=30)
        project.action_open_gathering()

        worker = self._make_person('Сторонний Работник')
        labour = self.Contribution.create({
            'project_id': project.id, 'partner_id': worker.partner_id.id,
            'kind': 'labour', 'name': 'Сварка', 'value': 20000,
            'state': 'offered'})
        labour.with_user(agent).action_accept()
        self.assertEqual(labour.state, 'accepted')
