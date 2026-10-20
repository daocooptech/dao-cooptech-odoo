# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTrialBalance(TransactionCase):
    """Оборотно-сальдовая ведомость: развёрнутое АП-сальдо, баланс, свёртка."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Account = cls.env['rsbu.account']
        cls.Move = cls.env['rsbu.move']
        cls.Wizard = cls.env['rsbu.trial.balance.wizard']
        cls.partner_a = cls.env['res.partner'].create({'name': 'Дебитор А'})
        cls.partner_b = cls.env['res.partner'].create({'name': 'Кредитор Б'})

    def _acc(self, code):
        return self.Account.search([
            ('code', '=', code),
            ('company_id', '=', self.company.id)], limit=1)

    def _post(self, lines, date='2026-02-10'):
        move = self.Move.create({
            'date': date,
            'line_ids': [(0, 0, l) for l in lines]})
        move.action_post()
        return move

    def test_expanded_balance_active_passive(self):
        """Счёт 62 (АП): дебиторка и кредиторка показаны РАЗВЁРНУТО.

        Партнёр А — долг (Дт 62.01 1000), партнёр Б — аванс (Кт 62.АВ 300).
        На синтетическом счёте 62 ОСВ должна показать Дт 1000 И Кт 300
        одновременно, а не нетто 700.
        """
        acc51 = self._acc('51')
        acc6201 = self._acc('62.01')
        acc62av = self._acc('62.АВ')
        # Дебиторка партнёра А: Дт 62.01 — Кт 51 (1000).
        self._post([
            {'account_id': acc6201.id, 'debit': 1000.0,
             'partner_id': self.partner_a.id},
            {'account_id': acc51.id, 'credit': 1000.0},
        ])
        # Аванс партнёра Б: Дт 51 — Кт 62.АВ (300).
        self._post([
            {'account_id': acc51.id, 'debit': 300.0},
            {'account_id': acc62av.id, 'credit': 300.0,
             'partner_id': self.partner_b.id},
        ])
        acc62 = self._acc('62')
        exp = acc62.get_expanded_balance(
            date_to='2026-02-28', company_id=self.company.id)
        self.assertEqual(exp['debit'], 1000.0,
                         'Дебиторка должна быть развёрнута в Дт')
        self.assertEqual(exp['credit'], 300.0,
                         'Аванс должен быть развёрнут в Кт')

    def test_wizard_generates_and_balances(self):
        """ОСВ: кон.сальдо = нач.сальдо + обороты (для активного счёта)."""
        acc51 = self._acc('51')
        acc62av = self._acc('62.АВ')
        # Поступление аванса: Дт 51 — Кт 62.АВ (2000) в феврале.
        self._post([
            {'account_id': acc51.id, 'debit': 2000.0},
            {'account_id': acc62av.id, 'credit': 2000.0,
             'partner_id': self.partner_a.id},
        ], date='2026-02-10')
        wiz = self.Wizard.create({
            'date_from': '2026-02-01', 'date_to': '2026-02-28',
            'company_id': self.company.id, 'hide_zero': True})
        wiz.action_generate()
        line51 = wiz.line_ids.filtered(lambda l: l.code == '51')
        self.assertTrue(line51, 'Счёт 51 должен присутствовать в ОСВ')
        # 51 активный: нач.сальдо 0, оборот Дт 2000, кон.сальдо Дт 2000.
        self.assertEqual(line51.opening_debit, 0.0)
        self.assertEqual(line51.turnover_debit, 2000.0)
        self.assertEqual(line51.closing_debit, 2000.0)
        # 62.АВ пассивный: оборот Кт 2000, кон.сальдо Кт 2000.
        line_av = wiz.line_ids.filtered(lambda l: l.code == '62.АВ')
        self.assertEqual(line_av.turnover_credit, 2000.0)
        self.assertEqual(line_av.closing_credit, 2000.0)

    def test_opening_balance_from_prior_period(self):
        """Нач.сальдо периода = проводки до date_from."""
        acc51 = self._acc('51')
        acc62av = self._acc('62.АВ')
        # Январь: аванс 500 (до периода).
        self._post([
            {'account_id': acc51.id, 'debit': 500.0},
            {'account_id': acc62av.id, 'credit': 500.0,
             'partner_id': self.partner_a.id},
        ], date='2026-01-20')
        # Февраль: ещё 700.
        self._post([
            {'account_id': acc51.id, 'debit': 700.0},
            {'account_id': acc62av.id, 'credit': 700.0,
             'partner_id': self.partner_a.id},
        ], date='2026-02-15')
        wiz = self.Wizard.create({
            'date_from': '2026-02-01', 'date_to': '2026-02-28',
            'company_id': self.company.id, 'hide_zero': True})
        wiz.action_generate()
        line51 = wiz.line_ids.filtered(lambda l: l.code == '51')
        # Нач.сальдо Дт 500 (январь), оборот Дт 700, кон.сальдо Дт 1200.
        self.assertEqual(line51.opening_debit, 500.0)
        self.assertEqual(line51.turnover_debit, 700.0)
        self.assertEqual(line51.closing_debit, 1200.0)

    def test_hide_zero_excludes_empty_accounts(self):
        """Опция «скрывать нулевые» убирает счета без данных."""
        acc51 = self._acc('51')
        acc62av = self._acc('62.АВ')
        self._post([
            {'account_id': acc51.id, 'debit': 100.0},
            {'account_id': acc62av.id, 'credit': 100.0,
             'partner_id': self.partner_a.id},
        ], date='2026-02-10')
        wiz = self.Wizard.create({
            'date_from': '2026-02-01', 'date_to': '2026-02-28',
            'company_id': self.company.id, 'hide_zero': True})
        wiz.action_generate()
        codes = set(wiz.line_ids.mapped('code'))
        # Счёт 80 (уставный капитал) без проводок — не должен попасть.
        self.assertNotIn('80', codes)
        self.assertIn('51', codes)
