from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCoopInvoicing(TransactionCase):
    """Режим НДС, счёт из сделки, функция УПД и доступ по полномочию."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env['res.partner']
        cls.seller = Partner.create({'name': 'ПК «Проба»', 'is_company': True})
        cls.buyer = Partner.create({'name': 'ООО «Покупка»', 'is_company': True})
        cls.keeper = cls._member('Казначей Пробы', ['treasury'])
        cls.member = cls._member('Член Пробы', ['publish'])
        cls.deal = cls.env['coop.deal'].create({
            'name': 'Поставка зерна',
            'way': 'sale',
            'party_a_id': cls.seller.id,
            'party_b_id': cls.buyer.id,
            'role_a': 'Продавец',
            'role_b': 'Покупатель',
            'amount': 105000.0,
            'state': 'done',
            'line_ids': [(0, 0, {'name': 'Зерно', 'quantity': 1, 'price_unit': 105000.0})],
        })
        cls.deal.act_confirmed_on = date(2026, 9, 1)

    @classmethod
    def _member(cls, name, codes):
        user = cls.env['res.users'].create({
            'name': name, 'login': name.replace(' ', '-').lower(),
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.env['coop.membership'].create({
            'partner_id': user.partner_id.id,
            'organization_id': cls.seller.id,
            'state': 'active',
            'admission_basis': 'Решение правления № 1',
            'power_ids': [(6, 0, cls.env['coop.power'].search([('code', 'in', codes)]).ids)],
        })
        return user

    def _regime(self, day, regime):
        return self.env['coop.vat.regime'].create(
            {'organization_id': self.seller.id, 'date_from': day, 'regime': regime})

    def test_regime_is_taken_on_shipping_date(self):
        self._regime('2026-01-01', 'exempt_145')
        self._regime('2026-07-01', 'usn_5')
        self.assertEqual(self.seller._coop_vat_regime_at(date(2026, 6, 30)), 'exempt_145')
        self.assertEqual(self.seller._coop_vat_regime_at(date(2026, 7, 1)), 'usn_5')
        self.assertFalse(self.seller._coop_vat_regime_at(date(2025, 12, 31)))

    def test_only_treasury_edits_regime_and_invoices(self):
        with self.assertRaises(AccessError):
            self.env['coop.vat.regime'].with_user(self.member).create(
                {'organization_id': self.seller.id, 'date_from': '2026-01-01', 'regime': 'usn_5'})
        self.env['coop.vat.regime'].with_user(self.keeper).create(
            {'organization_id': self.seller.id, 'date_from': '2026-01-01', 'regime': 'usn_5'})
        self.assertFalse(self.deal.with_user(self.member).coop_can_invoice)
        self.assertTrue(self.deal.with_user(self.keeper).coop_can_invoice)
        with self.assertRaises(UserError):
            self.deal.with_user(self.member).action_coop_create_invoice()

    def test_invoice_without_regime_is_refused(self):
        with self.assertRaises(UserError):
            self.deal.with_user(self.keeper).action_coop_create_invoice()

    def test_usn_5_gives_vat_invoice_for_deal_amount(self):
        self._regime('2026-01-01', 'usn_5')
        action = self.deal.with_user(self.keeper).action_coop_create_invoice()
        move = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(move.company_id, self.seller.coop_company_id)
        self.assertIn(self.seller.coop_company_id, self.keeper.company_ids)
        self.assertNotIn(self.seller.coop_company_id, self.member.company_ids)
        self.assertAlmostEqual(move.amount_total, 105000.0)
        self.assertAlmostEqual(move.amount_tax, 5000.0)
        move.action_post()
        self.assertEqual(move._coop_upd_function(), 'СЧФДОП')
        self.assertEqual(move._coop_upd_status(), '1')

    def test_exempt_gives_primary_document_and_blocks_tax(self):
        self._regime('2026-01-01', 'exempt_145')
        action = self.deal.with_user(self.keeper).action_coop_create_invoice()
        move = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(move.amount_tax, 0.0)
        self.assertEqual(move._coop_upd_function(), 'ДОП')
        self.assertEqual(move._coop_upd_status(), '2')
        move.invoice_line_ids.tax_ids = self.env['account.chart.template'].with_company(
            move.company_id).ref('sale_vat_22')
        with self.assertRaises(UserError):
            move.action_post()

    def test_access_follows_power(self):
        self._regime('2026-01-01', 'usn_5')
        self.deal.with_user(self.keeper).action_coop_create_invoice()
        company = self.seller.coop_company_id
        membership = self.env['coop.membership'].search([
            ('partner_id', '=', self.keeper.partner_id.id), ('organization_id', '=', self.seller.id)])
        membership.power_ids = [(5, 0, 0)]
        self.assertNotIn(company, self.keeper.company_ids)
