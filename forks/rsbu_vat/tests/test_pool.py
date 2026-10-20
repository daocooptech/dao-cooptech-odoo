"""Правки пула к РСБУ-слою (К5, задача 294): нумерация по организации,
дата закрытия периода от закрытия месяца, ставка 22 %."""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRsbuPool(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.rsbu_enabled = True
        cls.company.rsbu_usn_rate = 0.0
        cls.env['rsbu.account.load.wizard'].create({
            'company_id': cls.company.id}).action_load()
        cls.partner = cls.env['res.partner'].create({'name': 'Пул Клиент'})

    def _post(self, date, lines):
        Account = self.env['rsbu.account']
        move = self.env['rsbu.move'].create({
            'date': date, 'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'account_id': Account.search([
                    ('company_id', '=', self.company.id),
                    ('code', '=', code)]).id,
                'debit': d, 'credit': c}) for code, d, c in lines],
        })
        move.action_post()
        return move

    def _close(self, month):
        pc = self.env['rsbu.period.close'].create({
            'period_month': month, 'company_id': self.company.id})
        pc.action_close()
        return pc

    def test_invoice_numbering_per_company(self):
        other = self.env['res.company'].create({'name': 'Пул Вторая организация'})
        Invoice = self.env['rsbu.invoice']
        names = []
        for company in (other, other):
            names.append(Invoice.create({
                'invoice_type': 'advance', 'company_id': company.id,
                'partner_id': self.partner.id,
                'base_amount': 1000.0, 'vat_amount': 50.0}).name)
        self.assertTrue(names[0].endswith('1'), names)
        self.assertNotEqual(names[0], names[1])
        self.assertEqual(self.env['ir.sequence'].sudo().search_count([
            ('code', '=', 'rsbu.invoice'), ('company_id', '=', other.id)]), 1)

    def test_close_sets_lock_date_and_reopen_goes_backwards(self):
        self.company.rsbu_accounting_start = '2026-05-01'
        self._post('2026-05-20', [('26', 100.0, 0.0), ('51', 0.0, 100.0)])
        self._post('2026-06-20', [('26', 200.0, 0.0), ('51', 0.0, 200.0)])
        may = self._close('2026-05-01')
        self.assertEqual(str(self.company.rsbu_lock_date), '2026-05-31')
        june = self._close('2026-06-01')
        self.assertEqual(str(self.company.rsbu_lock_date), '2026-06-30')
        # В закрытый месяц задним числом не провести.
        with self.assertRaises(UserError):
            self._post('2026-06-25', [('26', 1.0, 0.0), ('51', 0.0, 1.0)])
        # Май раньше июня не переоткрыть.
        with self.assertRaises(UserError):
            may.action_reopen()
        june.action_reopen()
        self.assertEqual(str(self.company.rsbu_lock_date), '2026-05-31')
        self.assertEqual(june.state, 'draft')
        self._post('2026-06-25', [('26', 1.0, 0.0), ('51', 0.0, 1.0)])

    def test_vat_22(self):
        self.company.rsbu_vat_mode = 'vat_22'
        self.assertAlmostEqual(
            self.company._rsbu_vat_fraction_at('2027-01-15'), 22.0 / 122.0)
        tax = self.env['account.tax'].create({
            'name': 'НДС 22 % тест', 'amount': 22.0, 'type_tax_use': 'sale',
            'company_id': self.company.id})
        product = self.env['product.product'].create({'name': 'Товар 22'})
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id, 'quantity': 1, 'price_unit': 100.0,
                'tax_ids': [(6, 0, tax.ids)]})],
        })
        self.assertEqual(
            self.env['rsbu.realization']._upd_vat_rate(move), 'vat_22')
