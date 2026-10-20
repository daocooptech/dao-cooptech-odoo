from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestExtensionAccess(TransactionCase):
    """Модуль коробки у организации — руководителю и выбранным (решения 476, 480)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ext = cls.env['coop.extension'].search([
            ('module_name', '=', 'website_slides'), ('is_installed', '=', True)], limit=1)
        cls.org = cls.env['res.partner'].create({'name': 'ПК «Проба модулей»', 'is_company': True})
        cls.head = cls._member('Руководитель Пробы модулей', ['sign'])
        cls.member = cls._member('Член Пробы модулей', ['publish'])

    @classmethod
    def _member(cls, name, codes):
        user = cls.env['res.users'].create({
            'name': name, 'login': name.replace(' ', '-').lower(),
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.env['coop.membership'].create({
            'partner_id': user.partner_id.id, 'organization_id': cls.org.id,
            'state': 'active', 'admission_basis': 'Решение правления № 1',
            'power_ids': [(6, 0, cls.env['coop.power'].search([('code', 'in', codes)]).ids)],
        })
        return user

    def test_box_module_access_for_chosen(self):
        if not self.ext:
            self.skipTest('website_slides не установлен')
        group = self.ext._coop_module_groups()
        self.assertEqual(group, self.env.ref('website_slides.group_website_slides_officer'))
        conn = self.env['coop.extension.connection'].sudo().create({
            'partner_id': self.org.id, 'extension_id': self.ext.id,
            'access_user_ids': [(6, 0, self.head.ids)]})
        # Решение 480: компания учёта заведена, РСБУ-слой ждёт первого счёта.
        company = self.org.coop_company_id
        self.assertTrue(company)
        self.assertFalse(company.rsbu_enabled)
        self.assertTrue(company.coop_rsbu_pending)
        self.assertIn(group, self.head.group_ids)
        self.assertIn(company, self.head.company_ids)
        self.assertNotIn(group, self.member.group_ids)
        conn.access_user_ids = [(4, self.member.id)]
        self.assertIn(group, self.member.group_ids)
        conn.access_user_ids = [(3, self.member.id)]
        self.assertNotIn(group, self.member.group_ids)
        conn.unlink()
        self.assertNotIn(group, self.head.group_ids)
