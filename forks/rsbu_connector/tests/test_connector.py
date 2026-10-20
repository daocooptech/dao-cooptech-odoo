from unittest.mock import patch
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestRsbuConnector(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Cn Клиент'})
        cls.acc_51 = cls._acc(cls, '51')
        cls.acc_62av = cls._acc(cls, '62.АВ')
        # Простой входящий платёж.
        cls.journal_bank = cls.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', cls.company.id)],
            limit=1)

    def _acc(self, code):
        return self.env['rsbu.account'].search([
            ('code', '=', code),
            ('company_id', '=', self.env.company.id)], limit=1)

    def _balanced_lines(self):
        """Тестовый маппинг: Дт 51 — Кт 62.АВ на 1000."""
        return [
            {'account_id': self.acc_51.id, 'debit': 1000.0, 'credit': 0.0},
            {'account_id': self.acc_62av.id, 'debit': 0.0, 'credit': 1000.0,
             'partner_id': self.partner.id},
        ]

    def _patch_applicable(self):
        """Сделать документ применимым к РСБУ.

        Патчим методы на актуальном классе account.payment (в его MRO),
        чтобы патч работал независимо от того, переопределил ли их
        rsbu_mapping.
        """
        cls = type(self.env['account.payment'])
        return patch.object(cls, '_rsbu_is_applicable',
                            lambda self: True)

    def _patch_build_lines(self, lines):
        cls = type(self.env['account.payment'])
        return patch.object(cls, '_rsbu_build_lines',
                            lambda self: lines)

    def _make_payment(self):
        return self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner.id,
            'amount': 1000.0,
            'journal_id': self.journal_bank.id,
        })

    def test_generate_on_post(self):
        pay = self._make_payment()
        with self._patch_applicable(), \
                self._patch_build_lines(self._balanced_lines()):
            pay.action_post()
        self.assertTrue(pay.rsbu_move_id)
        self.assertEqual(pay.rsbu_move_id.state, 'posted')
        self.assertEqual(pay.rsbu_move_id.source_model, 'account.payment')
        self.assertEqual(pay.rsbu_move_id.source_res_id, pay.id)
        self.assertEqual(pay.rsbu_move_count, 1)

    def test_not_applicable_no_generation(self):
        # По умолчанию (Этап 3) документ не в РСБУ-периметре — проводится штатно.
        pay = self._make_payment()
        pay.action_post()
        self.assertFalse(pay.rsbu_move_id)

    def test_rsbu_skip_context(self):
        # Явный обход через контекст даже при применимости.
        pay = self._make_payment()
        with self._patch_applicable(), \
                self._patch_build_lines(self._balanced_lines()):
            pay.with_context(rsbu_skip=True).action_post()
        self.assertFalse(pay.rsbu_move_id)

    def test_no_mapping_blocks_post(self):
        # Документ применим, но маппинг не дал строк -> блок.
        pay = self._make_payment()
        with self._patch_applicable(), self.assertRaises(UserError):
            pay.action_post()

    def test_idempotent_double_post(self):
        pay = self._make_payment()
        with self._patch_applicable(), \
                self._patch_build_lines(self._balanced_lines()):
            pay.action_post()
            first = pay.rsbu_move_id
            pay._rsbu_generate()
        self.assertEqual(pay.rsbu_move_id, first)

    def test_mirror_on_cancel(self):
        pay = self._make_payment()
        with self._patch_applicable(), \
                self._patch_build_lines(self._balanced_lines()):
            pay.action_post()
        move = pay.rsbu_move_id
        self.assertTrue(move.exists())
        pay.action_cancel()
        self.assertFalse(pay.rsbu_move_id)
        self.assertFalse(move.exists())

    def test_mirror_then_repost_creates_new(self):
        pay = self._make_payment()
        with self._patch_applicable(), \
                self._patch_build_lines(self._balanced_lines()):
            pay.action_post()
            first_id = pay.rsbu_move_id.id
            pay.action_draft()
            self.assertFalse(pay.rsbu_move_id)
            pay.action_post()
            self.assertTrue(pay.rsbu_move_id)
            self.assertNotEqual(pay.rsbu_move_id.id, first_id)
