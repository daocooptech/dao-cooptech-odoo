# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_bounty_payment import CRITERIA, BountyCase


@tagged('post_install', '-at_install')
class TestBountyP2(BountyCase):
    """Улучшения П2, первый кусок (№ 465)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mate = cls.env['res.partner'].create({'name': 'Напарник проверочный'})
        cls.mate_user = cls.env['res.users'].create({
            'name': 'Напарник проверочный', 'login': 'bounty_mate',
            'partner_id': cls.mate.id,
            'group_ids': [(4, cls.env.ref('base.group_user').id)],
        })
        cls.admin = cls.env.ref('base.user_admin')

    def _apply(self, task, user):
        self.env['coop.bounty.apply'].with_user(user).create({
            'task_id': task.id, 'method_id': task.allowed_method_ids[:1].id}).action_confirm()
        return task.application_ids.filtered(lambda a: a.partner_id == user.partner_id)

    def _submit_as(self, task, user, link='https://cloud.daocoop.tech/s/p2'):
        self.env['coop.bounty.submit'].with_user(user).create({
            'task_id': task.id, 'link': link}).action_confirm()

    def _decide(self, task, outcome):
        self.env['coop.bounty.dispute'].with_user(self.admin).create({
            'task_id': task.id, 'outcome': outcome,
            'decision': 'Разобрано по критериям приёмки.'}).action_confirm()

    def test_partial_scale_pays_percent(self):
        task = self._platform_task(reward=300, partial_percent=40)
        task.action_publish()
        with self.assertRaises(UserError):
            task.partial_percent = 50
        self._apply_and_approve(task, 'tokens')
        self._submit(task)
        task.action_accept_partial()
        self.assertEqual((task.state, task.paid_amount, task.accepted_partially), ('accepted', 120, True))
        self.assertEqual(task.payout_ids.amount, 120)
        self.assertTrue(task.payout_ids.partial)
        self.assertEqual(task.reward_transaction_id.amount, 120)
        self.assertEqual((self.fund.paid, self.fund.reserved, self.fund.free), (120, 0, 880),
                         'фонд платит частичную сумму, остальное свободно')
        self.assertIn(task, self.Task.search(self.person._coop_bounty_done_domain()))

    def test_partial_needs_scale(self):
        task = self._platform_task(reward=300)
        task.action_publish()
        self._apply_and_approve(task, 'tokens')
        self._submit(task)
        with self.assertRaises(UserError):
            task.action_accept_partial()

    def test_team_splits_reward(self):
        task = self._platform_task(reward=301, executor_limit=2)
        task.action_publish()
        lead = self._apply(task, self.user)
        mate = self._apply(task, self.mate_user)
        lead.action_approve()
        self.assertEqual((task.state, task.assignee_id, task.member_count), ('published', self.person, 1),
                         'команда не собрана — задача открыта для заявок')
        mate.action_approve()
        self.assertEqual(task.state, 'assigned')
        self.assertEqual(task.member_ids.mapped('partner_id'), self.person | self.mate)
        with self.assertRaises(UserError):
            self._submit_as(task, self.mate_user)
        self._submit(task)
        task.criterion_ids.write({'done': True})
        task.action_accept()
        self.assertEqual(sorted(task.payout_ids.mapped('amount')), [150, 151])
        self.assertEqual(task.paid_amount, 301)
        self.assertEqual(sum(self.env['coop.token.transaction'].search(
            [('res_model', '=', task._name), ('res_id', '=', task.id)]).mapped('amount')), 301)
        self.assertIn(task, self.Task.search(self.mate._coop_bounty_done_domain()),
                      'участник команды видит задачу в выполненных')

    def test_team_shares_and_dissolve(self):
        task = self.Task.create({
            'name': 'Съёмка продукции', 'payer_id': self.org.id, 'project_id': self.project.id,
            'reward_tokens': 1000, 'criterion_ids': CRITERIA, 'executor_limit': 3,
        })
        task.action_publish()
        self._apply(task, self.user).action_approve()
        self._apply(task, self.mate_user).action_approve()
        self.assertEqual(task.state, 'published')
        task.action_start_team()
        self.assertEqual(task.state, 'assigned')
        task.member_ids.filtered(lambda m: m.partner_id == self.person).share_percent = 70
        task.member_ids.filtered(lambda m: m.partner_id == self.mate).share_percent = 20
        self._submit(task)
        task.criterion_ids.write({'done': True})
        with self.assertRaises(UserError):
            task.action_accept()
        task.member_ids.filtered(lambda m: m.partner_id == self.mate).share_percent = 30
        task.action_accept()
        moves = self.env['coop.project.token.move'].search([('task_id', '=', task.id)])
        self.assertEqual({m.partner_id: m.amount for m in moves}, {self.person: 700, self.mate: 300})
        self.assertEqual(self.project.coop_token_issued, 1000)

        other = self._platform_task(reward=100, executor_limit=2)
        other.action_publish()
        lead = self._apply(other, self.user)
        mate = self._apply(other, self.mate_user)
        (lead | mate).action_approve()
        lead.action_reject()
        self.assertEqual((other.state, other.assignee_id.id, other.member_count), ('published', False, 0),
                         'снят исполнитель — команда распущена')
        self.assertEqual(mate.state, 'applied')

    def test_recurring_pays_each_result_until_limit(self):
        task = self._platform_task(reward=100, is_recurring=True, repeat_limit=2)
        task.action_publish()
        self.assertEqual((self.fund.reserved, task.payment_mode), (200, 'tokens'),
                         'резерв постоянной задачи — за все результаты')
        with self.assertRaises(UserError):
            task.with_user(self.user).action_apply()
        self._submit_as(task, self.user)
        with self.assertRaises(UserError):
            self._submit_as(task, self.user)
        first = task.submission_ids
        self.assertEqual((first.partner_id, task.state), (self.person, 'published'))
        first.action_accept_result()
        self.assertEqual((task.paid_amount, task.repeat_done), (100, 1))
        self.assertEqual((self.fund.reserved, self.fund.paid), (100, 100))
        self._submit_as(task, self.mate_user)
        self._submit_as(task, self.user, link='https://cloud.daocoop.tech/s/p2v2')
        mine, theirs = (task.submission_ids.filtered(lambda s: s.state == 'review' and s.partner_id == p)
                        for p in (self.person, self.mate))
        theirs.action_accept_result()
        self.assertEqual((task.state, task.paid_amount), ('accepted', 200))
        self.assertEqual(mine.state, 'returned', 'лимит исчерпан — непроверенная сдача возвращена')
        self.assertEqual((self.fund.reserved, self.fund.free), (0, 800))
        self.assertEqual(task.payout_ids.mapped('partner_id'), self.person | self.mate)

    def test_recurring_return_one_result(self):
        task = self._platform_task(reward=100, is_recurring=True, repeat_limit=3)
        task.action_publish()
        self._submit_as(task, self.user)
        sub = task.submission_ids
        self.env['coop.bounty.return'].create({
            'task_id': task.id, 'submission_id': sub.id, 'note': 'Нет исходников'}).action_confirm()
        self.assertEqual((sub.state, task.state), ('returned', 'published'))
        self.assertTrue(task.with_user(self.user).can_submit_recurring)

    def test_executor_dispute_after_three_returns(self):
        task = self._platform_task(reward=200, partial_percent=50)
        task.action_publish()
        self._apply_and_approve(task, 'tokens')
        for _round in range(3):
            self.assertFalse(task.with_user(self.user).can_open_dispute)
            self._submit(task)
            task._coop_do_return('Доработать')
        self.assertTrue(task.with_user(self.user).can_open_dispute)
        self.assertFalse(task.with_user(self.mate_user).can_open_dispute, 'спор открывает исполнитель')
        self.env['coop.bounty.dispute.open'].with_user(self.user).create({
            'task_id': task.id, 'reason': 'Результат по критериям сдан трижды.'}).action_confirm()
        self.assertEqual((task.state, task.dispute_by), ('dispute', 'executor'))
        self._decide(task, 'partial')
        self.assertEqual((task.state, task.paid_amount, task.accepted_partially), ('accepted', 100, True))

    def test_executor_dispute_after_cancel(self):
        task = self._platform_task(reward=200)
        task.action_publish()
        self._apply_and_approve(task, 'tokens')
        self._submit(task)
        task.action_cancel()
        self.assertEqual(task.cancelled_on, fields.Date.today())
        self.assertTrue(task.with_user(self.user).can_open_dispute,
                        'исполнитель видит отменённую задачу и может её оспорить')
        task.cancelled_on = fields.Date.today() - timedelta(days=8)
        self.assertFalse(task.with_user(self.user).can_open_dispute, 'неделя на спор прошла')
        task.cancelled_on = fields.Date.today()
        self.env['coop.bounty.dispute.open'].with_user(self.user).create({
            'task_id': task.id, 'reason': 'Отменили после сдачи.'}).action_confirm()
        with self.assertRaises(UserError):
            self._decide(task, 'partial')
        self._decide(task, 'cancel')
        self.assertTrue(task.cancel_by_arbiter)
        self.assertFalse(task.with_user(self.user).can_open_dispute,
                         'отмену по решению спора не оспаривают')

    def test_median_hint_same_token(self):
        category = self.env['coop.specialization'].search([], limit=1).category_id
        spec = self.env['coop.specialization'].create({'name': 'Проверка медианы П2',
                                                       'category_id': category.id})
        for reward in (100, 200, 900):
            self._platform_task(reward=reward, coop_specialization_id=spec.id, state='accepted')
        self.Task.create({'name': 'Чужой токен', 'payer_id': self.org.id, 'project_id': self.project.id,
                          'reward_tokens': 5000, 'coop_specialization_id': spec.id, 'state': 'accepted'})
        task = self._platform_task(reward=150, coop_specialization_id=spec.id)
        self.assertTrue(task.median_hint.startswith('200 COOP — медиана 3 '), task.median_hint)
        project_task = self.Task.create({'name': 'Проект', 'payer_id': self.org.id,
                                         'project_id': self.project.id, 'coop_specialization_id': spec.id})
        self.assertFalse(project_task.median_hint, 'по токену проекта принятых задач меньше трёх')

    def test_author_answer_time(self):
        task = self._platform_task(reward=100, state='accepted', payer_id=self.org.id)
        today = fields.Date.today()
        Submission = self.env['coop.bounty.submission']
        for sent, answered in ((5, 2), (4, 0)):
            Submission.create({'task_id': task.id, 'partner_id': self.person.id, 'state': 'accepted',
                               'date': today - timedelta(days=sent),
                               'reviewed_on': today - timedelta(days=answered)})
        other = self._platform_task(reward=100, payer_id=self.org.id)
        self.assertEqual(other.payer_answer_label, 'за 3,5 дн. в среднем')
