# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestBountyPayment(TransactionCase):
    """Способы оплаты, фонд, потолок доли и спор (решения 671–673, 194)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Task = cls.env['coop.bounty.task']
        cls.Method = cls.env['coop.bounty.method']
        cls.m = {m.code: m for m in cls.Method.search([])}
        cls.fund = cls.env['coop.bounty.fund'].create({
            'name': 'Фонд для проверки', 'amount': 1000,
            'date_start': fields.Date.today() - timedelta(days=1),
            'date_end': fields.Date.today() + timedelta(days=90),
        })
        # Своему фонду — приоритет над фондом из данных модуля.
        cls.env['coop.bounty.fund'].search([('id', '!=', cls.fund.id)]).write(
            {'date_end': fields.Date.today() - timedelta(days=2)})
        cls.org = cls.env['res.partner'].create({
            'name': 'Пекарня проверочная', 'is_company': True,
            'coop_labor_share_cap': 10,
        })
        cls.person = cls.env['res.partner'].create({'name': 'Исполнитель проверочный'})
        cls.user = cls.env['res.users'].create({
            'name': 'Исполнитель проверочный', 'login': 'bounty_tester',
            'partner_id': cls.person.id,
            'group_ids': [(4, cls.env.ref('base.group_user').id)],
        })

    def _platform_task(self, reward=300, codes=('rub_offset', 'tokens')):
        return self.Task.create({
            'name': 'Задача платформы', 'reward_tokens': reward,
            'allowed_method_ids': [(6, 0, [self.m[c].id for c in codes])],
        })

    def _apply_and_approve(self, task, code):
        wizard = self.env['coop.bounty.apply'].with_user(self.user).create({
            'task_id': task.id, 'method_id': self.m[code].id})
        wizard.action_confirm()
        task.application_ids.action_approve()

    def test_platform_publish_reserves_fund(self):
        task = self._platform_task(reward=300)
        self.assertEqual(task.payer_kind, 'platform')
        task.action_publish()
        self.assertEqual(task.fund_id, self.fund)
        self.assertEqual(self.fund.reserved, 300)
        self.assertEqual(self.fund.free, 700)
        with self.assertRaises(UserError):
            task.write({'reward_tokens': 400})
        task.action_cancel()
        self.assertEqual(self.fund.free, 1000, 'отмена возвращает резерв в фонд')

    def test_platform_publish_without_enough_fund(self):
        task = self._platform_task(reward=1500)
        with self.assertRaises(UserError):
            task.action_publish()
        self.assertEqual(task.state, 'draft')

    def test_methods_required_and_scoped(self):
        task = self._platform_task(codes=())
        with self.assertRaises(UserError):
            task.action_publish()
        task.allowed_method_ids = [(6, 0, [self.m['share'].id])]
        task.share_percent = 5
        with self.assertRaises(UserError):
            task.action_publish()

    def test_project_share_cap(self):
        task = self.Task.create({
            'name': 'Логотип пекарни', 'payer_id': self.org.id,
            'allowed_method_ids': [(6, 0, [self.m['share'].id])],
            'share_percent': 15,
        })
        self.assertEqual(task.payer_kind, 'project')
        with self.assertRaises(UserError):
            task.action_publish()
        task.share_percent = 8
        task.action_publish()
        self.assertEqual(task.state, 'published')
        self.assertFalse(task.fund_id, 'задача проекта фонд платформы не трогает')

    def test_project_cannot_pay_platform_tokens(self):
        task = self.Task.create({
            'name': 'Сайт пекарни', 'payer_id': self.org.id, 'reward_tokens': 5000,
            'allowed_method_ids': [(6, 0, [self.m['tokens'].id])],
        })
        with self.assertRaises(UserError):
            task.action_publish()

    def test_executor_chooses_allowed_method(self):
        task = self.Task.create({
            'name': 'Фото продукции', 'payer_id': self.org.id, 'reward_tokens': 3000,
            'allowed_method_ids': [(6, 0, [self.m['rub'].id, self.m['project_tokens'].id])],
        })
        task.action_publish()
        with self.assertRaises(UserError):
            self.env['coop.bounty.apply'].with_user(self.user).create({
                'task_id': task.id, 'method_id': self.m['share'].id}).action_confirm()
        self._apply_and_approve(task, 'project_tokens')
        self.assertEqual(task.state, 'assigned')
        self.assertEqual(task.payment_mode, 'project_tokens')
        task.with_user(self.user).action_submit()
        task.action_accept()
        self.assertEqual(task.state, 'accepted')
        self.assertFalse(task.reward_transaction_id,
                         'токены платформы за задачу проекта не начисляются')

    def test_silence_opens_dispute_and_admin_decides(self):
        task = self._platform_task(reward=200)
        task.action_publish()
        self._apply_and_approve(task, 'tokens')
        task.with_user(self.user).action_submit()
        task.submitted_on = fields.Date.today() - timedelta(days=8)
        self.Task._cron_open_disputes()
        self.assertEqual(task.state, 'dispute', 'молчание автора — спор, не приёмка')
        decide = self.env['coop.bounty.dispute'].with_user(self.user).create({
            'task_id': task.id, 'outcome': 'assignee', 'decision': 'Результат сдан полностью.'})
        with self.assertRaises(UserError):
            decide.action_confirm()
        admin = self.env.ref('base.user_admin')
        self.env['coop.bounty.dispute'].with_user(admin).create({
            'task_id': task.id, 'outcome': 'assignee',
            'decision': 'Результат сдан полностью, автор не ответил.'}).action_confirm()
        self.assertEqual(task.state, 'accepted')
        self.assertEqual(task.reward_transaction_id.amount, 200)
        self.assertEqual(self.fund.paid, 200)
        self.assertTrue(task.dispute_decision)
