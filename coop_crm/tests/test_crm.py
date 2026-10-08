from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCoopCrm(TransactionCase):
    """CRM по полномочию «Сделки» и «Лид -> сделка площадки»."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env['res.partner']
        cls.org = Partner.create({'name': 'ПК «Проба CRM»', 'is_company': True})
        cls.client = Partner.create({'name': 'ООО «Клиент»', 'is_company': True})
        cls.env['coop.vat.regime'].create(
            {'organization_id': cls.org.id, 'date_from': '2026-01-01', 'regime': 'exempt_145'})
        # Без правовой формы по умолчанию только «Проекты»; CRM включает
        # руководитель (решение 450, приложения организации).
        cls.org.coop_app_crm = True
        cls.head = cls._member('Руководитель Пробы CRM', ['sign', 'represent'])
        cls.seller = cls._member('Продавец Пробы', ['deal', 'represent'])
        cls.keeper = cls._member('Казначей Пробы', ['treasury'])
        cls.org._coop_ensure_company()
        cls.env['res.users']._coop_sync_accounting_access(cls.org)

    @classmethod
    def _member(cls, name, codes):
        user = cls.env['res.users'].create({
            'name': name, 'login': name.replace(' ', '-').lower(),
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.env['coop.membership'].create({
            'partner_id': user.partner_id.id,
            'organization_id': cls.org.id,
            'state': 'active',
            'admission_basis': 'Решение правления № 1',
            'power_ids': [(6, 0, cls.env['coop.power'].search([('code', 'in', codes)]).ids)],
        })
        return user

    def test_access_by_power(self):
        company = self.org.coop_company_id
        self.assertIn(company, self.seller.company_ids)
        self.assertTrue(self.seller.has_group('sales_team.group_sale_salesman_all_leads'))
        self.assertFalse(self.seller.has_group('account.group_account_invoice'))
        self.assertTrue(self.keeper.has_group('account.group_account_invoice'))
        self.assertFalse(self.keeper.has_group('sales_team.group_sale_salesman'))
        team = self.env['crm.team'].search([('company_id', '=', company.id)])
        self.assertEqual(team.member_ids, self.seller)

    def test_lead_to_deal(self):
        company = self.org.coop_company_id
        lead = self.env['crm.lead'].with_user(self.seller).with_company(company).create({
            'name': 'Поставка льна', 'partner_id': self.client.id,
            'expected_revenue': 50000, 'type': 'opportunity',
        })
        action = lead.action_coop_create_deal()
        deal = self.env['coop.deal'].browse(action['res_id'])
        self.assertEqual(deal.party_a_id, self.org)
        self.assertEqual(deal.party_b_id, self.client)
        self.assertEqual(deal.amount, 50000)
        self.assertEqual(deal.state, 'draft')
        self.assertEqual(deal.coop_lead_id, lead)
        self.assertEqual(lead.coop_deal_id, deal)
        self.assertEqual(lead.won_status, 'won')

    def test_lead_without_client_or_power(self):
        company = self.org.coop_company_id
        lead = self.env['crm.lead'].with_user(self.seller).with_company(company).create(
            {'name': 'Без клиента', 'type': 'opportunity'})
        with self.assertRaises(UserError):
            lead.action_coop_create_deal()
        lead.partner_id = self.client
        with self.assertRaises(Exception):
            lead.with_user(self.keeper).action_coop_create_deal()

    def test_cabinet(self):
        deal = self.env['coop.deal'].sudo().create({
            'name': 'Поставка зерна', 'party_a_id': self.org.id,
            'party_b_id': self.client.id, 'state': 'lead'})
        page = self.org.with_user(self.seller)
        self.assertTrue(page.coop_is_org_staff)
        self.assertTrue(page.coop_can_see_funnel)
        self.assertEqual(page.coop_funnel_lead, 1)
        self.assertIn(self.seller.partner_id, page.coop_staff_ids.partner_id)
        # Казначей в составе, но воронка — держателям «Сделок».
        keeper_page = self.org.with_user(self.keeper)
        self.assertTrue(keeper_page.coop_is_org_staff)
        self.assertFalse(keeper_page.coop_can_see_funnel)
        action = page.action_coop_org_funnel()
        self.assertFalse(action['context']['coop_catalog'])
        self.assertEqual(action['context']['default_party_a_id'], self.org.id)
        membership = page.coop_staff_ids.filtered(
            lambda m: m.partner_id == self.seller.partner_id)
        self.assertEqual(membership.coop_open_deal_count, 1 if deal.responsible_a_id == self.seller else 0)

    def test_apps_by_head(self):
        company = self.org.coop_company_id
        # «Проекты» по умолчанию выключены (решение 452) — включаем, чтобы
        # проверить, что компания держится на последнем открытом приложении.
        self.org.with_user(self.head).write({'coop_app_project': True})
        with self.assertRaises(UserError):
            self.org.with_user(self.seller).write({'coop_app_crm': False})
        self.org.with_user(self.head).write({'coop_app_crm': False})
        self.assertFalse(self.seller.has_group('sales_team.group_sale_salesman_all_leads'))
        team = self.env['crm.team'].search([('company_id', '=', company.id)])
        self.assertFalse(team.member_ids)
        # Компания остаётся, пока открыты «Проекты»; выключены и они —
        # учёта организации у продавца больше нет.
        self.assertIn(company, self.seller.company_ids)
        self.org.with_user(self.head).write({'coop_app_project': False})
        self.assertNotIn(company, self.seller.company_ids)
        self.org.with_user(self.head).write({'coop_app_project': True})
        self.org.with_user(self.head).write({'coop_app_crm': True})
        self.assertTrue(self.seller.has_group('sales_team.group_sale_salesman_all_leads'))
        self.assertIn(company, self.seller.company_ids)

    def test_default_apps_by_form(self):
        group = self.env.ref('coop_base.legal_group_cooperative')
        form = self.env['coop.legal.form'].search([('group_id', '=', group.id)], limit=1)
        coop = self.env['res.partner'].create({
            'name': 'ПК «Набор по форме»', 'is_company': True,
            'coop_legal_form_id': form.id})
        self.assertTrue(coop.coop_app_crm and coop.coop_app_stock)
        # «Проекты» выключены у всех форм (решение 452).
        self.assertFalse(coop.coop_app_hr or coop.coop_app_project)
