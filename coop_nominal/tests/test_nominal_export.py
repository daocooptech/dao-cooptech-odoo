# -*- coding: utf-8 -*-
import base64
from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.coop_nominal_statement import parse_1c
from .test_nominal_statement import NominalStatementCase, _doc, _file

SELLER_ACCOUNT = '40702810000000000002'


@tagged('post_install', '-at_install')
class TestNominalExport(NominalStatementCase):
    """Реестр платёжек 1С и ежедневная сверка (этап 2в)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.account.write({'bank_bic': '044525225', 'bank_name': 'ПАО Сбербанк'})
        cls.env['res.partner.bank'].create({
            'partner_id': cls.seller.id, 'account_number': SELLER_ACCOUNT,
            'bank_name': 'Банк продавца', 'bank_bic': '044525593'})

    def _queued_payout(self, number=1, start='0.00', end='10000.00'):
        hold = self._hold()
        self._import([_doc(
            number, self.day, '10000.00', 'CT-%s' % hold.id, '500100732259',
            '40817810000000000001')], start=start, end=end)
        hold._act(self.today)
        hold._queue_payout()
        return hold, hold.payout_ids

    def _documents(self, batch):
        _header, _accounts, documents = parse_1c(batch.file.content)
        return documents

    def test_export_file_and_statement_closes_payout(self):
        hold, payout = self._queued_payout()
        batch = self.account._export_payouts()
        self.assertEqual(payout.state, 'sent')
        self.assertEqual(payout.batch_id, batch)
        self.assertEqual(payout.sent_on, self.today)
        self.assertEqual((batch.payout_count, batch.amount_total), (1, 9800.0))
        self.assertIn(b'\xcf\xeb\xe0\xf2\xe5\xe6\xed\xee\xe5',  # «Платежное» в 1251
                      batch.file.content)
        doc, = self._documents(batch)
        self.assertEqual(doc['Номер'], payout.order_number)
        self.assertEqual(doc['Сумма'], '9800.00')
        self.assertEqual(doc['ПлательщикСчет'], self.account.account_number)
        self.assertEqual(doc['ПолучательСчет'], SELLER_ACCOUNT)
        self.assertEqual(doc['ПолучательИНН'], '7707083893')
        self.assertEqual(doc['ПолучательБИК'], '044525593')
        self.assertTrue(doc['НазначениеПлатежа'].startswith('CT-%s.' % hold.id))
        # Списание по этой платёжке в выписке закрывает выплату.
        self._import([_doc(
            payout.order_number, self.day, '9800.00', doc['НазначениеПлатежа'],
            '7707083893', SELLER_ACCOUNT, incoming=False)], start='10000.00', end='200.00')
        self.assertEqual(payout.state, 'executed')
        self.assertEqual(hold.state, 'paid_out')

    def test_import_wizard_takes_file_from_browser(self):
        hold = self._hold()
        data = _file(self.day, self.day, '0.00', '10000.00', [_doc(
            1, self.day, '10000.00', 'CT-%s' % hold.id, '500100732259',
            '40817810000000000001')])
        # Браузер присылает файл base64-строкой.
        wizard = self.env['coop.nominal.statement.import'].create({
            'account_id': self.account.id,
            'file': base64.b64encode(data).decode(),
            'file_name': 'kl_to_1c.txt',
        })
        action = wizard.action_import()
        statement = self.env['coop.nominal.statement'].browse(action['res_id'])
        self.assertEqual(statement.file_name, 'kl_to_1c.txt')
        self.assertEqual(hold.state, 'held_buyer')

    def test_payout_goes_to_file_once(self):
        _hold, payout = self._queued_payout()
        first = self.account._export_payouts()
        with self.assertRaises(UserError):
            self.account._export_payouts()
        _hold2, payout2 = self._queued_payout(number=2, start='10000.00', end='20000.00')
        second = self.account._export_payouts()
        self.assertEqual(second.payout_ids, payout2)
        self.assertEqual(int(payout2.order_number), int(payout.order_number) + 1)
        with self.assertRaises(UserError):
            first.unlink()

    def test_refund_without_inn_matches_by_order_number(self):
        self._import([_doc(
            30, self.day, '700.00', 'Перевод', '', '40817810000000000099')], end='700.00')
        line = self.account.statement_ids.line_ids
        self.assertEqual(line.state, 'unrecognized')
        payout = line._resolve_refund()
        batch = self.account._export_payouts()
        doc, = self._documents(batch)
        self.assertIn('№30', doc['НазначениеПлатежа'])
        self.assertEqual(doc['ПолучательИНН'], '')
        self._import([_doc(
            payout.order_number, self.day, '700.00', 'Возврат', '',
            '40817810000000000099', incoming=False)], start='700.00', end='0.00')
        self.assertEqual(payout.state, 'executed')
        self.assertEqual(line.state, 'resolved')

    def test_export_refused_on_discrepancy_or_missing_requisites(self):
        _hold, payout = self._queued_payout()
        self.account.statement_balance += 1
        with self.assertRaises(UserError):
            self.account._export_payouts()
        self.account.statement_balance -= 1
        self.seller.bank_ids.unlink()
        payout.recipient_account = False
        with self.assertRaises(UserError):
            self.account._export_payouts()
        self.assertEqual(payout.state, 'queued')
        self.assertFalse(payout.batch_id)

    def test_frozen_hold_keeps_exported_payout(self):
        hold, payout = self._queued_payout()
        self.account._export_payouts()
        hold._freeze()
        self.assertEqual(payout.state, 'sent')
        self.assertEqual(hold.state, 'payout_queued')

    def test_daily_reconciliation(self):
        Reconciliation = self.env['coop.nominal.reconciliation']
        bare = self.account._reconcile()
        self.assertEqual(bare.state, 'problem')
        self.assertIn('ни разу', bare.note)

        self._import([_doc(
            40, self.day, '300.00', 'Без кода', '', '40817810000000000098')], end='300.00')
        record = self.account._reconcile()
        self.assertEqual(record, bare, 'сверка за день — одна запись')
        self.assertEqual(record.unrecognized_count, 1)
        self.assertEqual(record.state, 'problem')

        line = self.account.statement_ids.line_ids
        line._resolve_refund()
        self.account._export_payouts()
        later = self.today + timedelta(days=5)
        stale = self.account._reconcile(later)
        self.assertEqual(stale.stale_payout_count, 1)
        self.assertIn('Нет выписки', stale.note)
        self.assertEqual(Reconciliation.search_count(
            [('account_id', '=', self.account.id)]), 2)

    def test_reconciliation_ok(self):
        hold = self._hold()
        self._import([_doc(
            1, self.day, '10000.00', 'CT-%s' % hold.id, '500100732259',
            '40817810000000000001')], end='10000.00')
        record = self.account._reconcile()
        self.assertEqual(record.state, 'ok', record.note)
        self.assertFalse(record.discrepancy)
        self.assertEqual(record.ledger_balance, 10000.0)
