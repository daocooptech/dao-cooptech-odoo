# -*- coding: utf-8 -*-
"""Задача, оплаченная токенами, — доход в натуральной форме (решение 515)."""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.coop_base.tests.common import CoopCase


@tagged('post_install', '-at_install')
class TestNaturalIncome(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.coop = cls._make_org('Кооператив пробы натуральных доходов')
        cls.person = cls._make_person('Исполнитель пробы натуральных доходов').partner_id
        cls.Income = cls.env['coop.tax.natural.income']

    def _accept(self, mode='tokens', tokens=1000, payer=None, resident=True):
        self.person.write({'coop_tax_resident': resident, 'coop_tax_treaty_rate': 0})
        task = self.env['coop.bounty.task'].create({
            'name': 'Проба', 'reward_tokens': tokens, 'payment_mode': mode,
            'payer_id': (payer or self.coop).id, 'state': 'submitted',
            'assignee_id': self.person.id,
        })
        task.action_accept()
        return task

    def test_tokenami_v_reestr(self):
        task = self._accept()
        line = task.natural_income_ids
        self.assertEqual(len(line), 1)
        self.assertEqual((line.amount, line.ndfl_amount, line.rate), (1000, 130, '13 %'))
        self.assertEqual(line.state, 'calculated')
        self.assertEqual((task.natural_ndfl, task.natural_ndfl_state), (130, 'calculated'))

    def test_ispolnitel_organizaciya(self):
        studio = self._make_org('Студия пробы натуральных доходов')
        task = self.env['coop.bounty.task'].create({
            'name': 'Проба', 'reward_tokens': 1000, 'payment_mode': 'tokens',
            'payer_id': self.coop.id, 'state': 'submitted', 'assignee_id': studio.id,
        })
        task.action_accept()
        self.assertFalse(task.natural_income_ids)

    def test_zachetom_ne_v_reestr(self):
        task = self._accept(mode='rub_offset')
        self.assertFalse(task.natural_income_ids)
        self.assertEqual(task.reward_rub, 1000)

    def test_nerezident(self):
        line = self._accept(resident=False).natural_income_ids
        self.assertEqual((line.ndfl_amount, line.rate), (300, '30 % — нерезидент'))

    def test_uderzhanie_iz_vyplaty_paya(self):
        line = self._accept(tokens=10000).natural_income_ids  # НДФЛ 1300
        wallet = self.env['coop.wallet'].search([('partner_id', '=', self.person.id)], limit=1) \
            or self.env['coop.wallet'].create({'partner_id': self.person.id})
        account = self.env['coop.share.account'].create(
            {'wallet_id': wallet.id, 'cooperative_id': self.coop.id})
        Move = self.env['coop.share.move']
        today = line.date
        Move.create({'account_id': account.id, 'date': today, 'name': 'Начисление',
                     'kind': 'accrual', 'amount': 5000, 'basis': 'Протокол № 1'})
        payout = Move.create({'account_id': account.id, 'date': today, 'name': 'Выплата',
                              'kind': 'payout', 'amount': -2000, 'basis': 'Заявление',
                              'state': 'confirmed'})
        # Выплата 2000, свой НДФЛ 260, на руки до удержания 1740 — половина 870.
        self.assertEqual(payout.ndfl_amount, 260)
        self.assertEqual(payout.natural_withheld, 870)
        self.assertEqual(payout.net_amount, 870)
        self.assertEqual((line.withheld, line.remaining, line.state), (870, 430, 'calculated'))

    def test_proshlyi_god_i_soobshchenie(self):
        line = self._accept().natural_income_ids
        line.date = date(line.date.year - 1, 6, 1)
        self.assertEqual(line.state, 'not_withheld')
        action = line.action_fns_message()
        self.assertEqual(action['target'], 'download')
        self.assertTrue(line.reported_on)

    def test_soobshchenie_tolko_za_proshlyi_god(self):
        line = self._accept().natural_income_ids
        with self.assertRaises(UserError):
            line.action_fns_message()
