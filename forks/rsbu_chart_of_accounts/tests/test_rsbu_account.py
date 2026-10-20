from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError
from psycopg2 import IntegrityError
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestRsbuAccount(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env['rsbu.account']
        cls.company = cls.env.company
        cls.company2 = cls.env['res.company'].create({'name': 'RSBU Co2'})

    def _make(self, code, name='Счёт', kind='active', parent=None, **kw):
        vals = {'code': code, 'name': name, 'account_kind': kind}
        if parent:
            vals['parent_id'] = parent.id
        vals.update(kw)
        return self.Account.create(vals)

    def test_code_unique_per_company(self):
        self._make('T01')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self._make('T01')

    def test_code_reused_across_companies(self):
        a = self._make('T02')
        b = self._make('T02', company_id=self.company2.id)
        self.assertNotEqual(a.id, b.id)

    def test_no_cycle(self):
        a = self._make('T10')
        b = self._make('T11', parent=a)
        # Рекурсию ловит ядро parent_store (UserError "Recursion Detected")
        # ещё до нашего @api.constrains.
        with self.assertRaises(UserError):
            a.parent_id = b.id
            a.flush_recordset()

    def test_unlink_with_children_forbidden(self):
        a = self._make('T20')
        self._make('T21', parent=a)
        with self.assertRaises(ValidationError):
            a.unlink()

    def test_required_subconto(self):
        a = self._make('T30', subconto_partner=True, subconto_employee=True)
        self.assertEqual(set(a.get_required_subconto()), {'partner', 'employee'})

    def test_aggregation_zero_without_postings(self):
        a = self._make('T40')
        bal = a.get_balance()
        self.assertEqual(bal['debit'], 0.0)
        self.assertEqual(bal['credit'], 0.0)
        self.assertEqual(bal['balance'], 0.0)

    def test_subtree_ids(self):
        a = self._make('T50', is_group=True)
        b = self._make('T50.1', parent=a)
        c = self._make('T50.2', parent=a)
        ids = a._get_subtree_account_ids()
        self.assertIn(a.id, ids)
        self.assertIn(b.id, ids)
        self.assertIn(c.id, ids)

    def test_chart_loaded_for_company(self):
        # post_init_hook должен был загрузить типовой план для компании.
        acc51 = self.Account.search([
            ('code', '=', '51'), ('company_id', '=', self.company.id)])
        self.assertTrue(acc51, 'Счёт 51 должен быть загружен из типового плана')
        acc62av = self.Account.search([
            ('code', '=', '62.АВ'), ('company_id', '=', self.company.id)])
        self.assertTrue(acc62av, 'Субсчёт 62.АВ должен быть загружен')
        self.assertEqual(acc62av.parent_id.code, '62')
