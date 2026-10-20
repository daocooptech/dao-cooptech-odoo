from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRsbuOpeningBalance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'rsbu_enabled': True, 'rsbu_start_date': '2027-01-01'})
        cls.env['rsbu.account.load.wizard'].create({
            'company_id': cls.company.id}).action_load()
        cls.buyer = cls.env['res.partner'].create({'name': 'Остатки Покупатель'})
        cls.seller = cls.env['res.partner'].create({'name': 'Остатки Поставщик'})

    def _acc(self, code):
        return self.env['rsbu.account'].search([
            ('company_id', '=', self.company.id), ('code', '=', code)])

    def _wizard(self):
        wizard = self.env['rsbu.opening.balance.wizard'].create({
            'company_id': self.company.id})
        return wizard

    def test_manual_lines_against_000(self):
        wizard = self._wizard()
        self.assertEqual(str(wizard.date), '2026-12-31')
        wizard.line_ids = [
            (0, 0, {'account_id': self._acc('62.01').id,
                    'partner_id': self.buyer.id, 'debit': 1000.0}),
            (0, 0, {'account_id': self._acc('60').id,
                    'partner_id': self.seller.id, 'credit': 400.0}),
        ]
        action = wizard.action_post()
        move = self.env['rsbu.move'].browse(action['res_id'])
        self.assertEqual(move.state, 'posted')
        aux = move.line_ids.filtered(lambda l: l.account_id.code == '000')
        self.assertEqual(aux.credit, 600.0)
        balance = self._acc('62.01').get_balance(
            company_id=self.company.id, subconto={'partner': self.buyer.id})
        self.assertEqual(balance['balance'], 1000.0)

    def test_fill_from_accounting(self):
        product = self.env['product.product'].create({'name': 'Остатки Товар'})
        invoice = self.env['account.move'].with_context(rsbu_skip=True).create({
            'move_type': 'out_invoice', 'partner_id': self.buyer.id,
            'invoice_date': '2026-11-15', 'date': '2026-11-15',
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id, 'quantity': 1, 'price_unit': 500.0,
                'tax_ids': [(5, 0, 0)]})],
        })
        invoice.with_context(rsbu_skip=True).action_post()
        wizard = self._wizard()
        wizard.action_fill_from_accounting()
        line = wizard.line_ids.filtered(lambda l: l.partner_id == self.buyer)
        self.assertEqual(line.account_id.code, '62.01')
        self.assertEqual(line.debit, 500.0)
