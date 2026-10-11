# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

OUR = '40702810900000000777'


def _doc(number, date, amount, purpose, inn, account, incoming=True):
    """Документ выписки: поступление на наш счёт или списание с него."""
    us = {'Счет': OUR, 'ИНН': '7700000001', '1': 'ООО Оператор выписки'}
    them = {'Счет': account, 'ИНН': inn, '1': 'Контрагент %s' % inn}
    payer, payee = (them, us) if incoming else (us, them)
    lines = ['СекцияДокумент=Платежное поручение', 'Номер=%s' % number,
             'Дата=%s' % date, 'Сумма=%s' % amount]
    lines.append(('ДатаПоступило=%s' if incoming else 'ДатаСписано=%s') % date)
    for prefix, side in (('Плательщик', payer), ('Получатель', payee)):
        lines += ['%sСчет=%s' % (prefix, side['Счет']), '%sИНН=%s' % (prefix, side['ИНН']),
                  '%s1=%s' % (prefix, side['1']), '%sБИК=044525225' % prefix]
    lines += ['НазначениеПлатежа=%s' % purpose, 'КонецДокумента']
    return lines


def _file(date_from, date_to, start, end, docs, encoding='cp1251'):
    head = ['1CClientBankExchange', 'ВерсияФормата=1.03',
            'Кодировка=%s' % ('DOS' if encoding == 'cp866' else 'Windows'),
            'СекцияРасчСчет', 'ДатаНачала=%s' % date_from, 'ДатаКонца=%s' % date_to,
            'РасчСчет=%s' % OUR, 'НачальныйОстаток=%s' % start,
            'КонечныйОстаток=%s' % end, 'КонецРасчСчет']
    body = [line for doc in docs for line in doc]
    return '\r\n'.join(head + body + ['КонецФайла', '']).encode(encoding)


class NominalStatementCase(TransactionCase):
    """Счёт, стороны и сделка для проб выписки."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.context_today(cls.env['coop.nominal.hold'])
        cls.day = cls.today.strftime('%d.%m.%Y')
        Partner = cls.env['res.partner']
        cls.operator = Partner.create({
            'name': 'ООО «Оператор выписки»', 'is_company': True, 'vat': '7700000001'})
        cls.buyer = Partner.create({'name': 'Покупатель выписки', 'vat': '500100732259'})
        cls.seller = Partner.create({'name': 'Продавец выписки', 'vat': '7707083893'})
        cls.account = cls.env['coop.nominal.account'].create({
            'name': 'Номинальный счёт выписки',
            'owner_id': cls.operator.id,
            'account_number': OUR,
            'setting_ids': [(0, 0, {
                'date_from': cls.today - timedelta(days=30),
                'fee_percent': 2.0,
            })],
        })
        cls.deal = cls.env['coop.deal'].create({
            'name': 'Поставка яблок',
            'party_a_id': cls.seller.id,
            'party_b_id': cls.buyer.id,
        })

    def _hold(self, amount=10000.0):
        payment = self.env['coop.deal.payment'].create({
            'deal_id': self.deal.id, 'due_on': self.today, 'amount': amount,
            'payer_id': self.buyer.id, 'payee_id': self.seller.id,
        })
        return self.env['coop.nominal.hold'].create({
            'account_id': self.account.id, 'payment_id': payment.id,
            'payer_id': self.buyer.id, 'payee_id': self.seller.id, 'amount': amount,
        })

    def _import(self, docs, start='0.00', end='0.00', **kw):
        return self.account._import_statement(_file(self.day, self.day, start, end, docs, **kw))


@tagged('post_install', '-at_install')
class TestNominalStatement(NominalStatementCase):
    """Выписка 1С: зачисление по коду, нераспознанное, выплаты (этап 2а)."""

    def test_code_credits_hold_and_ledger_matches_bank(self):
        hold = self._hold()
        statement = self._import([_doc(
            1, self.day, '10000.00', 'Оплата по сделке ct %s, без НДС' % hold.id,
            '500100732259', '40817810000000000001')], end='10000.00')
        self.assertEqual(hold.state, 'held_buyer')
        self.assertEqual(hold.credited_on, self.today)
        self.assertEqual(hold.payment_id.state, 'paid')
        self.assertEqual(statement.line_ids.match_rule, 'code')
        self.assertEqual(hold.entry_ids.statement_line_id, statement.line_ids)
        self.assertEqual(self.account.statement_balance, 10000.0)
        self.assertFalse(self.account.discrepancy)
        self.assertFalse(self.account.payouts_blocked)

    def test_same_file_twice_and_overlapping_line(self):
        hold = self._hold()
        doc = _doc(7, self.day, '10000.00', 'CT-%s' % hold.id, '500100732259', '40817810000000000001')
        self._import([doc], end='10000.00')
        with self.assertRaises(UserError):
            self._import([doc], end='10000.00')
        # Та же строка в другой выписке (другой файл) второй раз не проводится.
        second = self._import([doc], start='0.00', end='10000.00', encoding='cp866')
        self.assertEqual(second.skipped_count, 1)
        self.assertFalse(second.line_ids)
        self.assertEqual(self.account.ledger_balance, 10000.0)

    def test_unknown_money_goes_to_unrecognized(self):
        statement = self._import([_doc(
            2, self.day, '777.00', 'Возврат долга', '123456789012', '40817810000000000009')],
            end='777.00')
        line = statement.line_ids
        self.assertEqual(line.state, 'unrecognized')
        self.assertTrue(line.note)
        self.assertEqual(self.account.unrecognized_balance, 777.0)
        # Книга сходится с банком и с нераспознанным: выплаты не блокирует
        # расхождение, а нераспознанное видно отдельно.
        self.assertFalse(self.account.discrepancy)

    def test_code_with_wrong_amount_is_not_credited(self):
        hold = self._hold()
        statement = self._import([_doc(
            3, self.day, '9000.00', 'CT-%s' % hold.id, '500100732259', '40817810000000000001')],
            end='9000.00')
        self.assertEqual(hold.state, 'awaiting')
        self.assertEqual(statement.line_ids.state, 'unrecognized')

    def test_inn_and_amount_without_code(self):
        hold = self._hold(amount=4321.0)
        self._hold(amount=5000.0)
        statement = self._import([_doc(
            4, self.day, '4321.00', 'За яблоки', '500100732259', '40817810000000000001')],
            end='4321.00')
        self.assertEqual(statement.line_ids.match_rule, 'inn_amount')
        self.assertEqual(hold.state, 'held_buyer')

    def test_two_codes_one_payment(self):
        first, second = self._hold(1000.0), self._hold(2000.0)
        self._import([_doc(
            5, self.day, '3000.00', 'CT-%s, CT-%s' % (first.id, second.id),
            '500100732259', '40817810000000000001')], end='3000.00')
        self.assertEqual((first | second).mapped('state'), ['held_buyer', 'held_buyer'])

    def test_outgoing_line_executes_payout(self):
        hold = self._hold()
        self._import([_doc(
            6, self.day, '10000.00', 'CT-%s' % hold.id, '500100732259', '40817810000000000001')],
            end='10000.00')
        hold._act(self.today)
        hold._queue_payout()
        payout = hold.payout_ids
        self.assertEqual(payout.amount, 9800.0)
        statement = self._import([
            _doc(8, self.day, '9800.00', 'Выплата по CT-%s' % hold.id, '7707083893',
                 '40702810000000000002', incoming=False),
            _doc(9, self.day, '200.00', 'Комиссия оператора', '7700000001',
                 '40702810000000000003', incoming=False),
        ], start='10000.00', end='0.00')
        self.assertEqual(payout.state, 'executed')
        self.assertEqual(hold.state, 'paid_out')
        self.assertEqual(hold.paid_out_on, self.today)
        self.assertEqual(statement.line_ids.mapped('match_rule'), ['payout', 'fee'])
        self.assertFalse(self.account.ledger_balance)
        self.assertFalse(self.account.discrepancy)

    def test_foreign_account_and_broken_file(self):
        data = _file(self.day, self.day, '0', '0', []).replace(OUR.encode(), b'40702810000000000000')
        with self.assertRaises(UserError):
            self.account._import_statement(data)
        broken = _file(self.day, self.day, '0', '0', []).replace('КонецФайла'.encode('cp1251'), b'')
        with self.assertRaises(UserError):
            self.account._import_statement(broken)

    def test_statement_is_immutable(self):
        statement = self._import([_doc(
            10, self.day, '1.00', 'Проба', '123456789012', '40817810000000000009')], end='1.00')
        with self.assertRaises(UserError):
            statement.write({'balance_end': 5.0})
        with self.assertRaises(UserError):
            statement.line_ids.write({'amount': 5.0})
        with self.assertRaises(UserError):
            statement.line_ids.unlink()


@tagged('post_install', '-at_install')
class TestNominalResolve(NominalStatementCase):
    """Ручной разбор нераспознанного (этап 2б)."""

    def _unknown_in(self, amount='5000.00', number=20, end=None):
        statement = self._import([_doc(
            number, self.day, amount, 'Оплата', '123456789012', '40817810000000000009')],
            end=end or amount)
        return statement.line_ids

    def test_unrecognized_paid_hold_by_hand(self):
        hold = self._hold(5000.0)
        line = self._unknown_in()
        self.assertEqual(line.state, 'unrecognized')
        found = self.env['coop.nominal.hold'].name_search('ct-%s' % hold.id)
        self.assertEqual([hold.id], [row[0] for row in found])
        self.assertTrue(hold.display_name.startswith('CT-%s' % hold.id))
        wizard = self.env['coop.nominal.statement.resolve'].create({
            'line_id': line.id, 'hold_ids': [(6, 0, hold.ids)]})
        self.assertEqual(wizard.mode, 'holds')
        wizard.action_apply()
        self.assertEqual(line.state, 'resolved')
        self.assertEqual(line.resolution, 'holds')
        self.assertEqual(hold.state, 'held_buyer')
        self.assertEqual(hold.credited_on, line.date)
        self.assertIn('recognize', hold.entry_ids.mapped('kind'))
        self.assertFalse(self.account.unrecognized_balance)
        self.assertFalse(self.account.discrepancy)
        with self.assertRaises(UserError):
            line._resolve_refund()

    def test_wrong_sum_is_refused(self):
        hold = self._hold(4000.0)
        line = self._unknown_in()
        with self.assertRaises(UserError):
            line._resolve_holds(hold)
        self.assertEqual(hold.state, 'awaiting')

    def test_refund_to_sender_closes_by_statement(self):
        line = self._unknown_in('777.00')
        refund = line._resolve_refund()
        self.assertEqual(refund.state, 'queued')
        self.assertEqual(refund.recipient_inn, '123456789012')
        self.assertEqual(refund.recipient_account, '40817810000000000009')
        self.assertEqual(refund.recipient_bic, '044525225')
        self.assertEqual(line.state, 'unrecognized')
        with self.assertRaises(UserError):
            line._resolve_refund()
        statement = self._import([_doc(
            21, self.day, '777.00', 'Возврат ошибочно перечисленных', '123456789012',
            '40817810000000000009', incoming=False)], start='777.00', end='0.00')
        self.assertEqual(statement.line_ids.match_rule, 'payout')
        self.assertEqual(refund.state, 'executed')
        self.assertEqual(line.state, 'resolved')
        self.assertEqual(line.resolution, 'refund')
        self.assertFalse(self.account.unrecognized_balance)
        self.assertFalse(self.account.ledger_balance)
        self.assertFalse(self.account.discrepancy)

    def test_unrecognized_debit_is_payout(self):
        hold = self._hold()
        self._import([_doc(
            22, self.day, '10000.00', 'CT-%s' % hold.id, '500100732259', '40817810000000000001')],
            end='10000.00')
        hold._act(self.today)
        hold._queue_payout()
        payout = hold.payout_ids
        # Банк списал без кода и на ИНН, которого у продавца в карточке нет.
        statement = self._import([_doc(
            23, self.day, '9800.00', 'Оплата по договору', '9909090909',
            '40702810000000000002', incoming=False)], start='10000.00', end='200.00')
        line = statement.line_ids
        self.assertEqual(line.state, 'unrecognized')
        self.assertEqual(payout.state, 'queued')
        self.assertEqual(self.account.unrecognized_balance, -9800.0)
        line._resolve_payout(payout)
        self.assertEqual(payout.state, 'executed')
        self.assertEqual(hold.state, 'paid_out')
        self.assertEqual(line.resolution, 'payout')
        self.assertFalse(self.account.unrecognized_balance)
        self.assertFalse(self.account.discrepancy)

    def test_offset_of_counter_lines(self):
        statement = self._import([
            _doc(24, self.day, '500.00', 'Ошибочное списание', '123456789012',
                 '40817810000000000009', incoming=False),
            _doc(25, self.day, '500.00', 'Возврат ошибочного списания', '123456789012',
                 '40817810000000000009'),
            _doc(26, self.day, '300.00', 'Прочее', '123456789012', '40817810000000000009'),
        ], end='300.00')
        out, back, other = statement.line_ids.sorted('number')
        with self.assertRaises(UserError):
            out._resolve_offset(other)
        out._resolve_offset(back)
        self.assertEqual((out | back).mapped('state'), ['resolved', 'resolved'])
        self.assertEqual(out.counterpart_line_id, back)
        self.assertEqual(self.account.unrecognized_balance, 300.0)
