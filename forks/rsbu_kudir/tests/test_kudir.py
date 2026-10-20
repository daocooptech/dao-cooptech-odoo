from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRsbuKudir(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Kudir Клиент'})
        cls.journal_bank = cls.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', cls.company.id)],
            limit=1)
        cls.Kudir = cls.env['rsbu.kudir.line']

    def _acc(self, code):
        return self.env['rsbu.account'].search([
            ('code', '=', code),
            ('company_id', '=', self.env.company.id)], limit=1)

    def _advance_template(self, recognition='income'):
        return self.env['rsbu.operation.template'].create({
            'code': 'ADV_IN_K',
            'name': 'Аванс',
            'resolver_key': 'advance_received',
            'usn_recognition': recognition,
            'role_ids': [
                (0, 0, {'role': 'bank', 'account_id': self._acc('51').id}),
                (0, 0, {'role': 'advance_received',
                        'account_id': self._acc('62.АВ').id}),
                (0, 0, {'role': 'vat_advance',
                        'account_id': self._acc('76.АВ').id}),
                (0, 0, {'role': 'vat_output',
                        'account_id': self._acc('68.НДС').id}),
            ],
        })

    def _matrix(self, template):
        return self.env['rsbu.operation.matrix'].create({
            'name': 'Входящий → аванс',
            'doc_kind': 'payment_inbound',
            'template_id': template.id,
        })

    def _post_advance(self, amount=1050.0, vat=50.0):
        pay = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner.id,
            'amount': amount,
            'rsbu_vat_amount': vat,
            'journal_id': self.journal_bank.id,
        })
        pay.action_post()
        return pay

    def test_recognition_carried_to_move(self):
        tmpl = self._advance_template('income')
        self._matrix(tmpl)
        pay = self._post_advance()
        self.assertEqual(pay.rsbu_move_id.usn_recognition, 'income')

    def test_kudir_income_recognized(self):
        tmpl = self._advance_template('income')
        self._matrix(tmpl)
        pay = self._post_advance(amount=1050.0, vat=50.0)
        move = pay.rsbu_move_id
        # НДС платежа (rsbu_vat_amount) исключается из дохода КУДиР:
        # на УСН+НДС доход отражается без предъявленного налога.
        self.assertEqual(move.kudir_income_vat, 50.0)
        self.Kudir.recompute_period(move.date, move.date, self.company)
        lines = self.Kudir.search([
            ('company_id', '=', self.company.id),
            ('section', '=', 'section_1')])
        self.assertTrue(lines)
        # Доход = поступление минус предъявленный НДС (1050 − 50 = 1000).
        total_income = sum(lines.mapped('income_amount'))
        self.assertEqual(total_income, 1000.0)

    def test_kudir_recompute_idempotent(self):
        tmpl = self._advance_template('income')
        self._matrix(tmpl)
        pay = self._post_advance()
        move = pay.rsbu_move_id
        self.Kudir.recompute_period(move.date, move.date, self.company)
        first = self.Kudir.search_count([('company_id', '=', self.company.id)])
        self.Kudir.recompute_period(move.date, move.date, self.company)
        second = self.Kudir.search_count([('company_id', '=', self.company.id)])
        self.assertEqual(first, second)

    def test_none_recognition_not_in_kudir(self):
        tmpl = self._advance_template('none')
        self._matrix(tmpl)
        pay = self._post_advance()
        move = pay.rsbu_move_id
        self.Kudir.recompute_period(move.date, move.date, self.company)
        lines = self.Kudir.search([('move_id', '=', move.id)])
        self.assertFalse(lines)

    def test_kudir_income_no_vat_full_amount(self):
        """Необлагаемое поступление (нет НДС, нет облагаемой реализации)
        признаётся доходом в полной сумме — НДС не исключается."""
        tmpl = self._advance_template('income')
        self._matrix(tmpl)
        pay = self._post_advance(amount=1000.0, vat=0.0)
        move = pay.rsbu_move_id
        # НДС платежа не задан и облагаемой реализации у партнёра нет —
        # исключать нечего.
        self.assertEqual(move.kudir_income_vat, 0.0)
        self.Kudir.recompute_period(move.date, move.date, self.company)
        lines = self.Kudir.search([
            ('company_id', '=', self.company.id),
            ('section', '=', 'section_1'),
            ('move_id', '=', move.id)])
        self.assertEqual(sum(lines.mapped('income_amount')), 1000.0)
