from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError


@tagged('post_install', '-at_install')
class TestRsbuMove(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env['rsbu.account']
        cls.Move = cls.env['rsbu.move']
        cls.company = cls.env.company
        # Счета из типового плана (загружен post_init_hook Этапа 1).
        cls.acc_51 = cls._acc(cls, '51')
        cls.acc_6201 = cls._acc(cls, '62.01')
        cls.acc_62av = cls._acc(cls, '62.АВ')
        cls.acc_90 = cls._acc(cls, '90')  # это группа? нет, синтетический
        cls.acc_9001 = cls._acc(cls, '90.01')
        cls.partner = cls.env['res.partner'].create({'name': 'Тест Клиент'})

    def _acc(self, code):
        return self.env['rsbu.account'].search([
            ('code', '=', code),
            ('company_id', '=', self.env.company.id)], limit=1)

    def _move(self, lines, date='2026-01-15'):
        return self.Move.create({
            'date': date,
            'line_ids': [(0, 0, l) for l in lines],
        })

    def test_post_balanced(self):
        move = self._move([
            {'account_id': self.acc_51.id, 'debit': 1000.0},
            {'account_id': self.acc_62av.id, 'credit': 1000.0,
             'partner_id': self.partner.id},
        ])
        move.action_post()
        self.assertEqual(move.state, 'posted')
        self.assertNotEqual(move.name, '/')

    def test_post_unbalanced_fails(self):
        move = self._move([
            {'account_id': self.acc_51.id, 'debit': 1000.0},
            {'account_id': self.acc_62av.id, 'credit': 900.0,
             'partner_id': self.partner.id},
        ])
        with self.assertRaises(UserError):
            move.action_post()

    def test_post_no_lines_fails(self):
        move = self.Move.create({'date': '2026-01-15'})
        with self.assertRaises(UserError):
            move.action_post()

    def test_line_one_side_only(self):
        with self.assertRaises(ValidationError):
            self._move([
                {'account_id': self.acc_51.id, 'debit': 100.0, 'credit': 100.0},
                {'account_id': self.acc_62av.id, 'credit': 100.0,
                 'partner_id': self.partner.id},
            ])

    def test_required_subconto_blocks_post(self):
        # 62.АВ требует партнёра — не заполняем.
        move = self._move([
            {'account_id': self.acc_51.id, 'debit': 500.0},
            {'account_id': self.acc_62av.id, 'credit': 500.0},
        ])
        with self.assertRaises(UserError):
            move.action_post()

    def test_draft_and_delete(self):
        move = self._move([
            {'account_id': self.acc_51.id, 'debit': 100.0},
            {'account_id': self.acc_62av.id, 'credit': 100.0,
             'partner_id': self.partner.id},
        ])
        move.action_post()
        move.action_draft()
        self.assertEqual(move.state, 'draft')
        move.unlink()  # из черновика — можно

    def test_delete_posted_fails(self):
        move = self._move([
            {'account_id': self.acc_51.id, 'debit': 100.0},
            {'account_id': self.acc_62av.id, 'credit': 100.0,
             'partner_id': self.partner.id},
        ])
        move.action_post()
        with self.assertRaises(UserError):
            move.unlink()

    def test_aggregation_after_post(self):
        move = self._move([
            {'account_id': self.acc_51.id, 'debit': 1500.0},
            {'account_id': self.acc_62av.id, 'credit': 1500.0,
             'partner_id': self.partner.id},
        ])
        move.action_post()
        bal_51 = self.acc_51.get_balance(company_id=self.company.id)
        self.assertEqual(bal_51['debit'], 1500.0)
        self.assertEqual(bal_51['balance'], 1500.0)
        self.assertEqual(bal_51['side'], 'debit')
        # 62.АВ пассивный — кредитовое сальдо.
        bal_av = self.acc_62av.get_balance(company_id=self.company.id)
        self.assertEqual(bal_av['credit'], 1500.0)
        self.assertEqual(bal_av['balance'], 1500.0)
        self.assertEqual(bal_av['side'], 'credit')

    def test_draft_moves_excluded_from_aggregation(self):
        move = self._move([
            {'account_id': self.acc_51.id, 'debit': 700.0},
            {'account_id': self.acc_62av.id, 'credit': 700.0,
             'partner_id': self.partner.id},
        ])
        # не проводим
        bal = self.acc_51.get_balance(company_id=self.company.id)
        self.assertEqual(bal['debit'], 0.0)

    def test_numbering_per_company(self):
        # Номера операций у каждой организации свои, не сквозь пул.
        other = self.env['res.company'].create({'name': 'Тест Вторая организация'})
        self.env.user.company_ids |= other
        moves = self.Move
        for company in (self.company, other, other):
            env = self.env(context=dict(self.env.context,
                                        allowed_company_ids=[company.id]))
            acc = env['rsbu.account'].search([
                ('company_id', '=', company.id), ('code', 'in', ('51', '90.01'))])
            by_code = {a.code: a for a in acc}
            move = env['rsbu.move'].create({
                'date': '2026-01-15',
                'company_id': company.id,
                'line_ids': [
                    (0, 0, {'account_id': by_code['51'].id, 'debit': 100.0}),
                    (0, 0, {'account_id': by_code['90.01'].id, 'credit': 100.0}),
                ],
            })
            move.action_post()
            moves |= move
        own, first, second = moves
        self.assertTrue(first.name.endswith('00001'), first.name)
        self.assertTrue(second.name.endswith('00002'), second.name)
        self.assertEqual(self.env['ir.sequence'].sudo().search_count([
            ('code', '=', 'rsbu.move'), ('company_id', '=', other.id)]), 1)
