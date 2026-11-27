# -*- coding: utf-8 -*-
"""Портфель паёв по видам пая с фактом начислений (решение 512)."""
from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestShareKinds512(TransactionCase):

    def setUp(self):
        super().setUp()
        Form = self.env['coop.legal.form']
        Partner = self.env['res.partner']

        def coop(name, code):
            form = Form.search([('code', '=', code)], limit=1)
            return Partner.create({'name': name, 'is_company': True,
                                   'coop_legal_form_id': form.id})
        self.po = coop('ПО «Тест-512»', 'po')
        self.zhsk = coop('ЖСК «Тест-512»', 'zhsk')
        self.kpk = coop('КПК «Тест-512»', 'kpk')
        self.wallet = self.env['coop.wallet'].wallet_for(self.env.user.partner_id)
        Account = self.env['coop.share.account']
        self.acc_po = Account.create({'wallet_id': self.wallet.id, 'cooperative_id': self.po.id})
        self.acc_zhsk = Account.create({'wallet_id': self.wallet.id, 'cooperative_id': self.zhsk.id})
        self.acc_kpk = Account.create({'wallet_id': self.wallet.id, 'cooperative_id': self.kpk.id})

    def _move(self, account, kind, amount, **extra):
        return self.env['coop.share.move'].create(dict({
            'account_id': account.id, 'date': date(2026, 3, 1), 'name': kind,
            'kind': kind, 'amount': amount, 'basis': 'Протокол № 1'}, **extra))

    def test_kind_follows_move_and_form(self):
        self.assertEqual(self._move(self.acc_po, 'share', 1000).share_kind, 'main')
        self.assertEqual(self._move(self.acc_po, 'extra', 5000).share_kind, 'extra')
        self.assertEqual(self._move(self.acc_zhsk, 'share', 90000).share_kind, 'premises')
        self.assertEqual(self._move(self.acc_kpk, 'savings_in', 100000).share_kind, 'savings')
        inc = self._move(self.acc_po, 'accrual', 700, share_kind='increment', redeem_from=date(2029, 1, 1))
        self.assertEqual(inc.share_kind, 'increment')

    def test_savings_are_not_share(self):
        self._move(self.acc_kpk, 'share', 1000)
        self._move(self.acc_kpk, 'savings_in', 100000)
        self._move(self.acc_kpk, 'savings_interest', 9000)
        self.assertEqual(self.acc_kpk.balance, 1000)
        self.assertEqual(self.acc_kpk.savings, 109000)

    def test_portfolio_rows_by_kind(self):
        self._move(self.acc_po, 'share', 1000)
        self._move(self.acc_po, 'extra', 50000)
        self._move(self.acc_po, 'accrual', 3000, share_kind='extra')
        self._move(self.acc_po, 'accrual', 700, share_kind='increment', redeem_from=date(2029, 1, 1))
        self._move(self.acc_zhsk, 'share', 90000)
        self._move(self.acc_kpk, 'savings_in', 100000)
        data = self.env['coop.portfolio'].snapshot()
        rows = {r['cooperative_id']: r for r in data['shares']}
        po = {k['key']: k for k in rows[self.po.id]['kinds']}
        self.assertEqual(set(po), {'main', 'extra', 'increment'})
        self.assertEqual(po['extra']['accrued_label'], 'Дивиденды')
        self.assertEqual(po['extra']['accrued'], 3000)
        self.assertEqual(po['extra']['balance'], 53000)
        self.assertEqual(po['increment']['note'], 'гасится с 2029 года')
        self.assertEqual(rows[self.zhsk.id]['kinds'][0]['note'], 'до перехода собственности')
        kpk = rows[self.kpk.id]['kinds'][0]
        self.assertEqual((kpk['key'], kpk['contributed']), ('savings', 100000))
        self.assertEqual(data['blocks']['shares']['savings'], 100000)
