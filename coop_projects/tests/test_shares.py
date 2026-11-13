# -*- coding: utf-8 -*-
"""Доля: одна правда вместо двух.

Правд было две, и они расходились у 684 принятых вкладов из 921: карточка
проекта показывала долю от рублей, реестр долей жил по начисленным долям.
Спор вкладчика с проектом свёлся бы к тому, какое из чисел настоящее.

Настоящее одно — по долям (решение владельца 294). Проверяется здесь,
потому что снаружи расхождение не видно: оба числа по отдельности
правдоподобны.
"""
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import CoopProjectCase


@tagged('post_install', '-at_install')
class TestProjectShares(CoopProjectCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'coop.project.share.rate' not in cls.env:
            cls.skip_all = True

    def _skip_without_tokenomics(self):
        if 'coop.project.share.rate' not in self.env:
            self.skipTest('Модуль токеномики не установлен')

    def test_dolya_schitaetsya_ot_doley_a_ne_ot_rubley(self):
        """Тысяча рублей труда весит больше тысячи рублей деньгами."""
        self._skip_without_tokenomics()
        project = self._make_project(state='gathering', required=200000)
        worker = self._make_person('Вложивший Труд')
        payer = self._make_person('Вложивший Деньги')

        labour = self.Contribution.create({
            'project_id': project.id, 'partner_id': worker.partner_id.id,
            'kind': 'labour', 'name': 'Сварка каркаса',
            'value': 100000, 'state': 'offered'})
        money = self.Contribution.create({
            'project_id': project.id, 'partner_id': payer.partner_id.id,
            'kind': 'money', 'name': 'Взнос', 'value': 100000,
            'state': 'offered'})
        labour.with_user(self.initiator).action_accept()
        money.with_user(self.initiator).action_accept()

        # 100 000 × 1,5 = 150 000 долей против 100 000 × 1,0.
        self.assertEqual(labour.share_tokens, 150000)
        self.assertEqual(money.share_tokens, 100000)
        self.assertEqual(labour.share_percent, 60)
        self.assertEqual(money.share_percent, 40)
        # А рублёвая сумма при этом делится поровну — это другой вопрос.
        self.assertEqual(project.contribution_total, 200000)

    def test_vklad_zavedyonnyy_srazu_prinyatym_poluchaet_doli(self):
        """Иначе в карточке выходит «×0»: вклад признан, доли нет."""
        self._skip_without_tokenomics()
        project = self._make_project(state='gathering')
        giver = self._make_person('Перенесённый Вкладчик')
        contribution = self.Contribution.create({
            'project_id': project.id, 'partner_id': giver.partner_id.id,
            'kind': 'material', 'name': 'Доски', 'value': 50000,
            'state': 'accepted'})
        self.assertTrue(contribution.share_tokens)
        self.assertEqual(contribution.share_factor_used, 1.3)

    def test_koeffitsient_deneg_nelzya_sdvinut(self):
        """Деньги — точка отсчёта, от неё меряются остальные."""
        self._skip_without_tokenomics()
        project = self._make_project()
        project.action_setup_share_rates()
        money = project.share_rate_ids.filtered(lambda r: r.kind == 'money')
        with self.assertRaises(ValidationError):
            money.factor = 0.5

    def test_stavki_zamorozheny_pervym_prinyatym_vkladom(self):
        """Доля, которая меняется задним числом, — не доля."""
        self._skip_without_tokenomics()
        project = self._make_project(state='gathering')
        giver = self._make_person('Ранний Вкладчик')
        offer = self._make_offer(project, giver, value=40000)
        offer.with_user(self.initiator).action_accept()

        labour = project.share_rate_ids.filtered(lambda r: r.kind == 'labour')
        with self.assertRaises(UserError):
            labour.factor = 1.9

    def test_koeffitsient_vne_diapazona_ne_prinimaetsya(self):
        """Ниже единицы он наказывает вид вклада, выше двух — отдаёт проект."""
        self._skip_without_tokenomics()
        project = self._make_project()
        project.action_setup_share_rates()
        labour = project.share_rate_ids.filtered(lambda r: r.kind == 'labour')
        with self.assertRaises(Exception):
            labour.factor = 2.5
            labour.flush_recordset()

    def test_vklad_v_kooperativ_tolko_chlenu(self):
        """Решение 676: нечлену вклад в кооперативный проект закрыт."""
        org = self._make_org('Артель Пробы Членства')
        org.coop_legal_form_id = self.env['coop.legal.form'].search(
            [('code', '=', 'artel')], limit=1)
        self.env['coop.membership'].create({
            'partner_id': self.initiator.partner_id.id,
            'organization_id': org.id, 'state': 'active',
            'admission_basis': 'Решение правления № 1',
            'power_ids': [(6, 0, self.env['coop.power'].search(
                [('code', 'in', ['deal', 'represent'])]).ids)],
        })
        member = self._make_person('Член Артели')
        self.env['coop.membership'].create({
            'partner_id': member.partner_id.id,
            'organization_id': org.id, 'state': 'active',
            'admission_basis': 'Решение правления № 2',
        })
        stranger = self._make_person('Посторонний Мастер')
        project = self._make_project(partner=org, state='gathering')
        self.assertTrue(project._coop_members_only())

        own = self.Contribution.create({
            'project_id': project.id, 'partner_id': member.partner_id.id,
            'kind': 'labour', 'name': 'Кладка', 'value': 60000,
            'state': 'offered'})
        alien = self.Contribution.create({
            'project_id': project.id, 'partner_id': stranger.partner_id.id,
            'kind': 'resource', 'name': 'Экскаватор', 'value': 40000,
            'state': 'offered'})
        own.with_user(self.initiator).action_accept()
        self.assertEqual(own.state, 'accepted')
        with self.assertRaises(UserError):
            alien.with_user(self.initiator).action_accept()

        # Окно вклада нечлену форму не даёт.
        wizard = self.env['coop.project.contribute'].with_user(
            stranger).create({'project_id': project.id, 'kind': 'resource',
                              'name': 'Экскаватор', 'value': 40000})
        self.assertTrue(wizard.members_only)
        self.assertEqual(wizard.member_state, 'none')
        with self.assertRaises(UserError):
            wizard.action_offer()

        # Демо приводится к правилу приёмом в члены.
        self.Project._coop_admit_contributors()
        self.assertTrue(project._coop_is_member(stranger.partner_id))
