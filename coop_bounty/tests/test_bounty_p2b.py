# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from .test_bounty_payment import CRITERIA, BountyCase


@tagged('post_install', '-at_install')
class TestBountyP2b(BountyCase):
    """Улучшения П2, второй кусок (№ 465): конкурс, этапы, резерв проекта."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mate = cls.env['res.partner'].create({'name': 'Конкурсант проверочный'})
        cls.mate_user = cls.env['res.users'].create({
            'name': 'Конкурсант проверочный', 'login': 'bounty_contest_mate',
            'partner_id': cls.mate.id,
            'group_ids': [(4, cls.env.ref('base.group_user').id)],
        })
        cls.today = fields.Date.today()

    def _send(self, task, user, link='https://cloud.daocoop.tech/s/contest'):
        self.env['coop.bounty.submit'].with_user(user).create({
            'task_id': task.id, 'link': link}).action_confirm()

    def _contest(self, prizes=(300, 150), **extra):
        values = {'is_contest': True, 'deadline': self.today + timedelta(days=5),
                  'prize_ids': [(0, 0, {'place': n + 1, 'amount': amount})
                                for n, amount in enumerate(prizes)]}
        values.update(extra)
        return self._platform_task(reward=0, **values)

    def _result(self, task, places):
        wizard = self.env['coop.bounty.contest.result'].with_context(
            default_task_id=task.id).create({'task_id': task.id})
        for line in wizard.line_ids:
            line.place = places.get(line.partner_id, '0')
        return wizard

    def _result_form(self, task, places):
        """Как в окне: строки правятся в форме, на сервер уходит только видимое."""
        form = Form(self.env['coop.bounty.contest.result'].with_context(default_task_id=task.id))
        for index in range(len(form.line_ids)):
            with form.line_ids.edit(index) as line:
                line.place = places.get(line.partner_id, '0')
        return form.save()

    # ── Конкурс ──────────────────────────────────────────────────────────

    def test_contest_flow(self):
        task = self._contest()
        task.action_publish()
        self.assertEqual((task.reward_tokens, task.payment_mode), (450, 'tokens'))
        self.assertEqual(self.fund.reserved, 450, 'резервируется сумма всех мест')
        with self.assertRaises(UserError):
            task.with_user(self.user).action_apply()
        self._send(task, self.user)
        with self.assertRaises(UserError):
            self._send(task, self.user)
        self._send(task, self.mate_user)
        self.assertEqual(task.contest_entry_count, 2)
        self.assertFalse(task.can_sum_up, 'до срока итог не подводят')
        with self.assertRaises(UserError):
            task.action_accept()

        task.deadline = self.today - timedelta(days=1)
        self.Task._cron_contest_deadline()
        self.assertEqual(task.state, 'submitted')
        self.assertTrue(task.can_sum_up)
        with self.assertRaises(UserError):
            self._result(task, {self.mate: '2'}).action_confirm()
        self._result_form(task, {self.person: '1'}).action_confirm()

        self.assertEqual((task.state, task.paid_amount, task.assignee_id), ('accepted', 300, self.person))
        self.assertEqual(task.payout_ids.mapped('prize_place'), [1])
        self.assertEqual(task.prize_ids.filtered(lambda p: p.place == 1).winner_id, self.person)
        self.assertEqual(task.submission_ids.filtered(lambda s: s.partner_id == self.mate).state, 'not_won')
        self.assertEqual((self.fund.paid, self.fund.reserved, self.fund.free), (300, 0, 700),
                         'не присуждённое второе место не выплачено и вернулось в фонд')

    def test_contest_without_entries_closes(self):
        task = self._contest()
        task.action_publish()
        task.deadline = self.today - timedelta(days=1)
        self.Task._cron_contest_deadline()
        self.assertEqual(task.state, 'cancelled')
        self.assertEqual(self.fund.free, 1000)

    def test_contest_rules(self):
        with self.assertRaises(ValidationError):
            self._contest(executor_limit=2)
        task = self._contest(prizes=(100, 200))
        with self.assertRaises(UserError):
            task.action_publish()
        task = self._contest(deadline=False)
        with self.assertRaises(UserError):
            task.action_publish()
        task = self._platform_task(reward=0, is_contest=True,
                                   deadline=self.today + timedelta(days=3),
                                   prize_ids=[(0, 0, {'place': 2, 'amount': 100})])
        with self.assertRaises(UserError):
            task.action_publish()

    def test_contest_dispute_by_silence_is_summed_by_arbiter(self):
        task = self._contest(prizes=(200,))
        task.action_publish()
        self._send(task, self.user)
        task.deadline = self.today - timedelta(days=10)
        self.Task._cron_contest_deadline()
        self.Task._cron_open_disputes()
        self.assertEqual(task.state, 'dispute')
        with self.assertRaises(UserError):
            self.env['coop.bounty.dispute'].create({
                'task_id': task.id, 'outcome': 'assignee', 'decision': 'Засчитать.'}).action_confirm()
        wizard = self._result(task, {self.person: '1'})
        with self.assertRaises(UserError):
            wizard.action_confirm()
        wizard.decision = 'Работа одна и соответствует условиям конкурса.'
        wizard.action_confirm()
        self.assertEqual((task.state, task.paid_amount), ('accepted', 200))
        self.assertTrue(task.dispute_decision)

    # ── Этапы ────────────────────────────────────────────────────────────

    def _staged(self, **extra):
        values = {
            'name': 'Сайт пекарни', 'payer_id': self.org.id, 'project_id': self.project.id,
            'reward_tokens': 0, 'criterion_ids': CRITERIA,
            'stage_ids': [(0, 0, {'name': 'Макет', 'amount': 1000, 'sequence': 1}),
                          (0, 0, {'name': 'Вёрстка', 'amount': 2000, 'sequence': 2})],
        }
        values.update(extra)
        return self.Task.create(values)

    def test_stages_pay_each(self):
        task = self._staged()
        task.action_publish()
        self.assertEqual(task.reward_tokens, 3000, 'сумма задачи — сумма этапов')
        self.assertEqual(self.project.coop_bounty_blocked, 3000)
        with self.assertRaises(UserError):
            task.stage_ids[0].amount = 1500
        self._apply_and_approve(task, 'project_tokens')
        self._submit(task)
        first, second = task.stage_ids.sorted('sequence')
        self.assertEqual(first.state, 'review')
        task.action_accept()
        self.assertEqual((task.state, task.paid_amount, first.state), ('assigned', 1000, 'accepted'))
        self.assertEqual(task.payout_ids.stage_id, first)
        self.assertEqual(task.stage_current_id, second)
        self.assertEqual((self.project.coop_bounty_blocked, self.project.coop_bounty_paid), (2000, 1000))

        self._submit(task)
        with self.assertRaises(UserError):
            task.action_accept()
        task.criterion_ids.write({'done': True})
        task.action_accept()
        self.assertEqual((task.state, task.paid_amount, second.state), ('accepted', 3000, 'accepted'))
        self.assertEqual(sorted(task.payout_ids.mapped('amount')), [1000, 2000])
        moves = self.env['coop.project.token.move'].search([('task_id', '=', task.id)])
        self.assertEqual(sum(moves.mapped('amount')), 3000)
        self.assertEqual(self.project.coop_bounty_blocked, 0)

    def test_stage_return_and_no_draft_after_payout(self):
        task = self._staged()
        task.action_publish()
        self._apply_and_approve(task, 'project_tokens')
        self._submit(task)
        task._coop_do_return('Макет без мобильной версии.')
        self.assertEqual(task.stage_ids.sorted('sequence')[0].state, 'todo')
        self._submit(task)
        task.action_accept()
        task.action_cancel()
        self.assertEqual(self.project.coop_bounty_blocked, 0, 'отмена освобождает остаток')
        with self.assertRaises(UserError):
            task.action_reset_to_draft()

    def test_single_stage_is_not_staged(self):
        task = self._staged(stage_ids=[(0, 0, {'name': 'Всё сразу', 'amount': 500})])
        with self.assertRaises(UserError):
            task.action_publish()

    # ── Резерв задачи проекта (решение 689) ─────────────────────────────

    def test_project_reserve(self):
        project = self.env['coop.project'].create({
            'name': 'Сыроварня — проверка', 'partner_id': self.org.id,
            'coop_token_name': 'Токен сыроварни', 'coop_token_symbol': 'CHEESE'})
        task = self.Task.create({'name': 'Этикетка', 'payer_id': self.org.id,
                                 'project_id': project.id, 'reward_tokens': 800,
                                 'criterion_ids': CRITERIA})
        with self.assertRaises(UserError):
            task.action_publish()
        project.coop_bounty_token_limit = 1000
        big = self.Task.create({'name': 'Упаковка', 'payer_id': self.org.id,
                                'project_id': project.id, 'reward_tokens': 1500,
                                'criterion_ids': CRITERIA})
        with self.assertRaises(UserError):
            big.action_publish()
        task.action_publish()
        self.assertEqual((project.coop_bounty_blocked, project.coop_bounty_free), (800, 200))
        self.assertIn('заблокировано у проекта', task.reserve_label)
        with self.assertRaises(ValidationError):
            project.coop_bounty_token_limit = 500
        project.coop_bounty_token_limit = 0
        project._coop_bounty_fit_limit()
        self.assertEqual(project.coop_bounty_token_limit, 1000, 'с запасом в четверть, круглым числом')
        task.action_cancel()
        self.assertEqual((project.coop_bounty_blocked, project.coop_bounty_free), (0, 1000))
