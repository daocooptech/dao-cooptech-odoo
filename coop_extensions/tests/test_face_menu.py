# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFaceMenu(TransactionCase):
    """Меню по лицу (решения 463, 468): человек — своё, организация — общее."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.org = cls.env['res.partner'].create(
            {'name': 'ПК «Проба меню»', 'is_company': True})
        cls.head = cls._member('Руководитель Пробы меню', ['sign', 'site'])
        cls.seller = cls._member('Продавец Пробы меню', ['deal'])
        Ext = cls.env['coop.extension'].sudo()
        cls.waiting = Ext.search([('source', '=', 'odoo'), ('module_id', '!=', False),
                                  ('is_installed', '=', False)], limit=1)
        cls.ready = Ext.search([('module_name', '=', 'coop_documents'),
                                ('is_installed', '=', True)], limit=1)

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

    def _ext_labels(self, user):
        items = self.env['coop.sidebar.item'].with_user(user).items_for_current_user()
        return {i['label']: i for i in items if i['section'] == 'ext'}

    def test_person_connect_waiting_module(self):
        """Модуля нет — пункт встаёт «устанавливается», каталог видит заявку."""
        if not self.waiting:
            self.skipTest('нет неустановленного модуля коробки')
        ext = self.waiting.with_user(self.seller)
        self.assertEqual(ext.coop_connect_state, 'off')
        ext.action_coop_connect()
        ext.invalidate_recordset()
        self.assertEqual(ext.coop_connect_state, 'installing')
        item = self._ext_labels(self.seller)[self.waiting.name]
        self.assertFalse(item['actionId'])
        self.assertTrue(item['pending'])
        self.assertIn(self.waiting, self.env['coop.extension'].with_user(self.seller).search(
            [('coop_connected', '=', True)]))
        ext.action_coop_disconnect()
        self.assertNotIn(self.waiting.name, self._ext_labels(self.seller))

    def test_person_defaults_count_as_connected(self):
        """Выданные платформой пункты каталог видит подключёнными."""
        if not self.ready:
            self.skipTest('нет coop_documents')
        self._ext_labels(self.seller)
        self.assertEqual(self.ready.with_user(self.seller).coop_connect_state, 'on')

    def test_org_menu_is_shared_and_led_by_head(self):
        self.seller.coop_acting_as_id = self.org
        self.head.coop_acting_as_id = self.org
        labels = self._ext_labels(self.seller)
        # Тот же набор, что у людей (владелец 18.10.2026).
        if self.ready:
            self.assertIn('Документы', labels)
        if not self.waiting:
            return
        with self.assertRaises(UserError):
            self.waiting.with_user(self.seller).action_coop_connect()
        self.waiting.with_user(self.head).action_coop_connect()
        self.assertTrue(self._ext_labels(self.seller)[self.waiting.name]['pending'])
        # Личное меню продавца от этого не меняется.
        self.seller.coop_acting_as_id = False
        self.assertNotIn(self.waiting.name, self._ext_labels(self.seller))
        # Убрать из меню организации может только руководитель.
        self.seller.coop_acting_as_id = self.org
        with self.assertRaises(UserError):
            self.waiting.with_user(self.seller).action_coop_disconnect()
        self.waiting.with_user(self.head).action_coop_disconnect()
        self.assertNotIn(self.waiting.name, self._ext_labels(self.seller))

    def test_no_crm_in_person_menu(self):
        if 'crm.lead' not in self.env:
            self.skipTest('нет crm')
        self.assertNotIn('CRM', self._ext_labels(self.seller))
