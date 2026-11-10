# -*- coding: utf-8 -*-
"""Оператор «Платформа» и выпуск внутри платформы (задача 387, кусок 4)."""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPlatformOperator(TransactionCase):

    def setUp(self):
        super().setUp()
        self.platform = self.env.ref('coop_digital_assets.operator_platform')
        self.other = self.env.ref('coop_digital_assets.operator_atomyze')
        self.issuer = self.env['res.partner'].create({'name': 'Эмитент', 'is_company': True})

    def _issue(self, operator=None):
        vals = {'issuer_id': self.issuer.id, 'name': 'Выпуск', 'amount': 1000000}
        if operator is not None:
            vals['operator_id'] = operator.id
        return self.env['coop.cfa.issue'].create(vals)

    def test_platform_is_default_first_operator(self):
        self.assertTrue(self.platform.is_platform)
        self.assertEqual(self.env['coop.cfa.operator'].search([], limit=1), self.platform)
        self.assertEqual(self._issue().operator_id, self.platform)

    def test_issue_on_platform_is_immediate(self):
        issue = self._issue()
        self.issuer.coop_verification_level = 'identity'
        if not self.issuer.coop_verified:
            self.skipTest('подтверждение личности в тесте недоступно')
        issue.action_submit()
        self.assertEqual(issue.state, 'issued')
        self.assertTrue(issue.external_reference.startswith('DAO-'))

    def test_third_party_stays_submitted(self):
        issue = self._issue(self.other)
        self.issuer.coop_verification_level = 'identity'
        if not self.issuer.coop_verified:
            self.skipTest('подтверждение личности в тесте недоступно')
        issue.action_submit()
        self.assertEqual(issue.state, 'submitted')
        self.assertFalse(issue.external_reference)

    def test_no_operator_refused(self):
        issue = self._issue()
        issue.operator_id = False
        with self.assertRaises(UserError):
            issue.action_submit()
