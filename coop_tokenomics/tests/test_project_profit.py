# -*- coding: utf-8 -*-
"""Объявление прибыли проекта и распределение по долям (задача 387, кусок 1)."""
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProjectProfit(TransactionCase):

    def setUp(self):
        super().setUp()
        Partner = self.env['res.partner']
        self.owner = Partner.create({'name': 'Инициатор'})
        self.a = Partner.create({'name': 'Вкладчик А'})
        self.b = Partner.create({'name': 'Вкладчик Б'})
        self.c = Partner.create({'name': 'Вкладчик В'})
        self.project = self._project('commercial')
        for partner, value in ((self.a, 100000), (self.b, 50000), (self.c, 30000)):
            self.env['coop.project.contribution'].create({
                'project_id': self.project.id, 'partner_id': partner.id,
                'name': 'Вклад', 'kind': 'money', 'value': value,
                'state': 'accepted',
            })

    def _project(self, kind):
        return self.env['coop.project'].create({
            'name': 'Проект %s' % kind, 'kind': kind,
            'partner_id': self.owner.id,
            'currency_id': self.env.ref('base.RUB').id,
        })

    def _profit(self, amount=100001.0, project=None):
        return self.env['coop.project.profit'].create({
            'project_id': (project or self.project).id,
            'period_from': '2026-07-01', 'period_to': '2026-09-30',
            'amount': amount,
        })

    def test_distribution_sums_to_amount(self):
        profit = self._profit(100001.0)
        profit.action_compute()
        self.assertEqual(len(profit.line_ids), 3)
        self.assertAlmostEqual(profit.distributed_total, 100001.0, places=2)
        top = profit.line_ids.sorted('amount', reverse=True)[0]
        self.assertEqual(top.partner_id, self.a)
        self.assertAlmostEqual(top.share_percent, 55.5556, places=3)
        self.assertEqual(profit.withheld_total, 0)

    def test_declare_computes_and_sets_state(self):
        profit = self._profit()
        profit.action_declare()
        self.assertEqual(profit.state, 'declared')
        self.assertTrue(profit.line_ids)
        with self.assertRaises(UserError):
            profit.action_compute()
        profit.action_cancel()
        self.assertEqual(profit.state, 'cancelled')
        profit.action_to_draft()
        self.assertEqual(profit.state, 'draft')

    def test_only_commercial_and_dao(self):
        for kind in ('cooperative', 'nonprofit'):
            with self.assertRaises(ValidationError):
                self._profit(project=self._project(kind))
        self._profit(project=self._project('dao'))

    def test_bad_amount_and_period(self):
        with self.assertRaises(ValidationError):
            self._profit(0)
        with self.assertRaises(ValidationError):
            self.env['coop.project.profit'].create({
                'project_id': self.project.id, 'amount': 10,
                'period_from': '2026-09-30', 'period_to': '2026-07-01'})

    def test_no_contributions(self):
        profit = self._profit(project=self._project('commercial'))
        with self.assertRaises(UserError):
            profit.action_compute()

    def test_pay_credits_wallets_once(self):
        profit = self._profit(100001.0)
        with self.assertRaises(UserError):
            profit.action_pay()
        profit.action_declare()
        profit.action_pay()
        self.assertEqual(profit.state, 'paid')
        moves = profit.line_ids.mapped('movement_id')
        self.assertEqual(len(moves), 3)
        self.assertEqual(set(moves.mapped('kind')), {'profit'})
        self.assertAlmostEqual(sum(moves.mapped('amount')), 100001.0, places=2)
        for line in profit.line_ids:
            self.assertEqual(line.movement_id.partner_id, line.partner_id)
        with self.assertRaises(UserError):
            profit.action_pay()
        with self.assertRaises(UserError):
            profit.action_cancel()
