# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .test_bounty_payment import BountyCase


@tagged('post_install', '-at_install')
class TestTaskTokens(BountyCase):
    """Токены исполнителю задачи в управлении проектом (№ 485)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups = [(4, cls.env.ref('project.group_project_manager').id)]
        cls.user.group_ids = groups
        base = [(4, cls.env.ref('base.group_user').id)]
        cls.boss = cls.env['res.users'].create({
            'name': 'Менеджер проверочный', 'login': 'token_boss', 'group_ids': base + groups})
        cls.mate = cls.env['res.users'].create({
            'name': 'Второй проверочный', 'login': 'token_mate', 'group_ids': base + groups})
        cls.work = cls.env['project.project'].create({
            'name': 'Работа пекарни', 'user_id': cls.boss.id})
        cls.project.project_id = cls.work
        cls.Move = cls.env['coop.project.token.move']

    def _task(self, tokens=300, users=None, project=None, name='Испечь хлеб', emission=False):
        return self.env['project.task'].with_user(self.boss).with_context(
            coop_no_emission=not emission).create({
            'name': name, 'project_id': (project or self.work).id,
            'coop_tokens': tokens, 'user_ids': [(6, 0, (users or self.user).ids)]})

    def _moves(self, task):
        return self.Move.search([('work_task_id', '=', task.id)])

    def test_manager_done_pays_once(self):
        task = self._task()
        task.write({'state': '1_done'})
        self.assertEqual(self._moves(task).mapped('amount'), [300])
        self.assertEqual(self._moves(task).partner_id, self.person)
        task.write({'state': '01_in_progress'})
        task.write({'state': '1_done'})
        self.assertEqual(task.coop_tokens_paid, 300)
        self.assertEqual(len(self._moves(task)), 1)
        self.project.invalidate_recordset()
        self.assertEqual(self.project.coop_bounty_free, 49700)
        with self.assertRaises(UserError):
            task.coop_tokens = 900
        with self.assertRaises(UserError):
            task.user_ids = self.mate
        self.assertIn('300', self.work.with_user(self.boss).coop_an_tokens)

    def test_executor_cannot_pay_himself(self):
        task = self._task()
        mine = task.with_user(self.user)
        with self.assertRaises(UserError):
            mine.coop_tokens = 5000
        mine.write({'state': '1_done'})
        self.assertFalse(self._moves(task))
        self.assertTrue(mine.coop_token_waits)
        with self.assertRaises(UserError):
            mine.action_coop_tokens_accept()
        task.action_coop_tokens_accept()
        self.assertEqual(task.coop_tokens_paid, 300)

    def test_executor_required(self):
        task = self._task()
        with self.assertRaises(ValidationError):
            task.user_ids = [(5,)]
        bare = self.env['project.task'].with_user(self.boss).create({
            'name': 'Без исполнителя', 'project_id': self.work.id, 'user_ids': [(5,)]})
        self.assertEqual(bare.user_ids, self.boss)

    def test_split_and_limit(self):
        task = self._task(tokens=101, users=self.user | self.mate)
        task.write({'state': '1_done'})
        self.assertEqual(sorted(self._moves(task).mapped('amount')), [50, 51])
        big = self._task(tokens=60000)
        big.write({'state': '1_done'})
        self.assertFalse(big.coop_tokens_paid)
        with self.assertRaises(UserError):
            big.action_coop_tokens_accept()

    def _ours(self):
        ours = self.Task._coop_our_project()
        work = self.env['project.project'].create({'name': 'Доска', 'user_id': self.boss.id})
        ours.project_id = work
        return ours, work

    def test_our_project_from_fund(self):
        _ours, work = self._ours()
        task = self._task(project=work)
        task.write({'state': '1_done'})
        bounty = self.Task.search([('work_task_id', '=', task.id)])
        self.assertEqual((bounty.state, bounty.assignee_id, bounty.paid_amount),
                         ('accepted', self.person, 300))
        self.fund.invalidate_recordset()
        self.assertEqual(self.fund.paid, 300)
        self.assertEqual(self.person.coop_token_balance, 300)
        poor = self._task(project=work, tokens=900)
        poor.write({'state': '1_done'})
        self.assertFalse(poor.coop_tokens_paid)
        self.fund.invalidate_recordset()
        self.assertEqual(self.fund.paid, 300)

    def test_our_project_published_task(self):
        ours, work = self._ours()
        bounty = self._platform_task(project_id=ours.id, coop_source_ref='vault:99901')
        bounty.action_publish()
        task = self._task(project=work, tokens=0, name='99901. Задача списка')
        task._coop_tokens_adopt()
        self.assertEqual(task.coop_tokens, 300)
        task.coop_tokens = 400
        task.write({'state': '1_done'})
        self.fund.invalidate_recordset()
        self.assertEqual((bounty.state, bounty.paid_amount, self.fund.reserved), ('accepted', 400, 0))
        self.assertEqual(self.Task.search_count([('coop_source_ref', '=', 'vault:99901')]), 1)

    def test_emission_on_create(self):
        task = self._task(tokens=700, emission=True)
        self.assertEqual((self.project.coop_bounty_token_limit, task.coop_tokens_emitted), (50700, 700))
        task.coop_tokens = 1000
        self.assertEqual(self.project.coop_bounty_token_limit, 51000)
        task.coop_tokens = 400
        self.assertEqual((self.project.coop_bounty_token_limit, task.coop_tokens_emitted), (50400, 400))
        _ours, work = self._ours()
        ours_task = self._task(tokens=5000, project=work, emission=True)
        self.assertEqual(self.fund.amount, 6000)
        ours_task.write({'state': '1_done'})
        self.assertEqual(ours_task.coop_tokens_paid, 5000)
        self.fund.invalidate_recordset()
        self.assertEqual(self.fund.free, 1000)
        # Оценка прежней задачи, под которую не выпускали, фонд не уменьшает.
        old = self._task(tokens=300)
        old.with_context(coop_no_emission=False).coop_tokens = 100
        self.assertEqual(self.project.coop_bounty_token_limit, 50400)

    def test_cancel_withdraws(self):
        limit = lambda: self.project.coop_bounty_token_limit
        task = self._task(tokens=700, emission=True)
        task.write({'state': '1_canceled'})
        self.assertEqual((limit(), task.coop_tokens_emitted), (50000, 0))
        task.coop_tokens = 900
        task.write({'state': '01_in_progress'})
        self.assertEqual((limit(), task.coop_tokens_emitted), (50900, 900))
        task.active = False
        self.assertEqual(limit(), 50000)
        task.active = True
        self.assertEqual(limit(), 50900)
        task.unlink()
        self.assertEqual(limit(), 50000)
        # Под прежнюю задачу не выпускали — изымать нечего; оплаченная не трогается.
        self._task(tokens=300).write({'state': '1_canceled'})
        paid = self._task(tokens=200, emission=True)
        paid.write({'state': '1_done'})
        paid.write({'state': '1_canceled'})
        self.assertEqual(limit(), 50200)
        _ours, work = self._ours()
        own = self._task(tokens=5000, project=work, emission=True)
        own.write({'state': '1_canceled'})
        self.assertEqual(self.fund.amount, 1000)

    def test_crowd_emission(self):
        self.boss.group_ids = [(4, self.env.ref('coop_bounty.group_coop_community_manager').id)]
        values = {'name': 'Задача платформы', 'reward_tokens': 5000,
                  'payer_id': self.env.company.partner_id.id,
                  'allowed_method_ids': [(6, 0, [self.m['tokens'].id])],
                  'criterion_ids': [(0, 0, {'name': 'Готово'})]}
        Crowd = self.Task.with_user(self.boss)
        task = Crowd.create(values)
        self.assertEqual((self.fund.amount, task.coop_tokens_emitted), (6000, 5000))
        task.reward_tokens = 4000
        self.assertEqual(self.fund.amount, 5000)
        task.action_publish()
        self.fund.invalidate_recordset()
        self.assertEqual((self.fund.reserved, self.fund.free), (4000, 1000))
        task.action_cancel()
        self.assertEqual(self.fund.amount, 1000)
        own = Crowd.create(dict(values, payer_id=self.org.id, project_id=self.project.id,
                                allowed_method_ids=[(6, 0, [self.m['project_tokens'].id])]))
        self.assertEqual(self.project.coop_bounty_token_limit, 55000)
        own.unlink()
        self.assertEqual(self.project.coop_bounty_token_limit, 50000)
        # Система и список платформы не выпускают.
        self._platform_task()
        self.assertEqual(self.fund.amount, 1000)
