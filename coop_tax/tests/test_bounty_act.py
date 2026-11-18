# -*- coding: utf-8 -*-
"""Статус исполнителя до утверждения и акт при приёмке (№ 465 п. 20)."""
import re

from odoo.tests import tagged

from odoo.addons.coop_base.tests.common import CoopCase


@tagged('post_install', '-at_install')
class TestBountyAct(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.coop = cls._make_org('Кооператив пробы актов')
        cls.person = cls._make_person('Исполнитель пробы актов').partner_id
        cls.App = cls.env['coop.bounty.application']

    def _accept(self, tokens=1000):
        task = self.env['coop.bounty.task'].create({
            'name': 'Проба акта', 'reward_tokens': tokens, 'payment_mode': 'tokens',
            'payer_id': self.coop.id, 'state': 'submitted', 'assignee_id': self.person.id,
        })
        task.action_accept()
        return task

    def test_status_before_approval(self):
        self.person.write({'coop_tax_regime': 'npd', 'coop_tax_resident': True})
        note, warning = self.App._coop_tax_texts(self.person, self.coop)
        self.assertIn('Самозанятый', note)
        self.assertFalse(warning)
        self.person.write({'coop_tax_regime': 'none', 'coop_tax_resident': False})
        note, warning = self.App._coop_tax_texts(self.person, self.coop)
        self.assertIn('договор ГПХ', note)
        self.assertIn('не налоговый резидент', warning.lower())
        self.person.write({'coop_tax_regime': 'usn_income'})
        self.assertIn('ИП', self.App._coop_tax_texts(self.person, self.coop)[0])
        note, warning = self.App._coop_tax_texts(self.coop, self.person)
        self.assertIn('Организация', note)
        self.assertFalse(warning, 'у организации-исполнителя резидентство человека не спрашивают')

    def test_act_on_payout(self):
        self.person.write({'coop_tax_regime': 'none', 'coop_tax_resident': True})
        task = self._accept()
        payout = task.payout_ids
        self.assertTrue(re.match(r'^\d{4}-\d{5}$', payout.act_number or ''), payout.act_number)
        self.assertEqual((payout.executor_status, payout.executor_resident), ('gph', True))
        self.person.coop_tax_regime = 'npd'
        self.assertEqual(payout.executor_status, 'gph', 'статус в акте — на день выплаты')
        html, _kind = self.env['ir.actions.report']._render_qweb_html(
            'coop_tax.report_bounty_act', payout.ids)
        html = html.decode()
        self.assertIn(payout.act_number, html)
        self.assertIn('Проба акта', html)
        second = self._accept(tokens=500).payout_ids
        self.assertNotEqual(second.act_number, payout.act_number)
