# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMoneySettings(TransactionCase):
    """Деньги и реквизиты: рубль по умолчанию, у организации — «Казначейство»."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.org = cls.env['res.partner'].create({'name': 'ТСН «Проба денег»', 'is_company': True})
        cls.keeper = cls._member('Казначей Пробы Денег', ['treasury', 'represent'])
        cls.clerk = cls._member('Представитель Пробы Денег', ['represent'])
        cls.method = cls.env['coop.settlement.method'].search([('status', '!=', 'planned')], limit=1)

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

    def test_rouble_by_default(self):
        self.assertEqual(self.org.coop_payout_currency_id, self.env.ref('base.RUB'))

    def test_treasury_edits_org_money(self):
        org = self.org.with_user(self.keeper)
        self.assertTrue(org.coop_can_edit_money)
        org.write({'coop_tax_regime': 'usn_income',
                   'coop_settlement_method_ids': [(4, self.method.id)]})
        self.assertEqual(self.org.coop_tax_regime, 'usn_income')
        self.assertIn(self.method, self.org.coop_settlement_method_ids)
        other = self.org.with_user(self.clerk)
        self.assertFalse(other.coop_can_edit_money)
        with self.assertRaises(UserError):
            other.write({'coop_tax_regime': 'osno'})

    def test_own_money(self):
        me = self.clerk.partner_id.with_user(self.clerk)
        self.assertTrue(me.coop_can_edit_money)
        me.write({'coop_settlement_method_ids': [(4, self.method.id)]})
        self.assertIn(self.method, self.clerk.partner_id.coop_settlement_method_ids)
