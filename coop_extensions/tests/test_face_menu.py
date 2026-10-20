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

    def test_new_person_has_no_given_extensions(self):
        """Расширения платформа не выдаёт: только разделы, дальше — из каталога."""
        if not self.ready:
            self.skipTest('нет coop_documents')
        self.assertNotIn('Документы', self._ext_labels(self.seller))
        ext = self.ready.with_user(self.seller)
        self.assertEqual(ext.coop_connect_state, 'off')
        ext.action_coop_connect()
        ext.invalidate_recordset()
        self.assertEqual(ext.coop_connect_state, 'on')
        self.assertIn('Документы', self._ext_labels(self.seller))

    def test_person_cannot_connect_org_accounting(self):
        """Учёт организации человеку не подключить: внутри было бы «нет доступа»."""
        stock = self.env['coop.extension'].sudo().search(
            [('module_name', '=', 'stock'), ('is_installed', '=', True)], limit=1)
        if not stock or self.seller.has_group('stock.group_stock_user'):
            self.skipTest('нет склада или у продавца есть права склада')
        with self.assertRaises(UserError):
            stock.with_user(self.seller).action_coop_connect()

    def test_org_menu_is_shared_and_led_by_head(self):
        self.seller.coop_acting_as_id = self.org
        self.head.coop_acting_as_id = self.org
        # Набора по умолчанию нет (владелец 19.10.2026).
        self.assertNotIn('Документы', self._ext_labels(self.seller))
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

    def test_org_access_tab_instead_of_org_menu(self):
        """Экрана «Меню организации» нет: «Доступ у» — во вкладке «Настроек»
        «Права доступа», «Настроить меню» от организации — только разделы
        (решение 481 п. 5)."""
        self.assertFalse(self.env.ref('coop_extensions.action_coop_org_menu',
                                      raise_if_not_found=False))
        self.head.coop_acting_as_id = self.org
        boot = self.env['coop.shell'].with_user(self.head).boot()
        self.assertEqual(boot['menuSettings'], self.env.ref(
            'coop_extensions.action_coop_sidebar_sections').id)
        Conn = self.env['coop.extension.connection']
        if not self.waiting:
            return
        self.waiting.with_user(self.head).action_coop_connect()
        action = Conn.with_user(self.head).action_coop_open_access()
        rows = Conn.with_user(self.head).search(action['domain'])
        self.assertEqual(rows.extension_id, self.waiting)
        self.assertEqual(rows.access_user_ids, self.head)
        self.assertTrue(rows.coop_can_manage)
        # Продавец видит, но отмечать людей не вправе.
        self.assertFalse(rows.with_user(self.seller).coop_can_manage)
        with self.assertRaises(UserError):
            rows.with_user(self.seller).access_user_ids = [(4, self.seller.id)]
        rows.with_user(self.head).access_user_ids = [(4, self.seller.id)]
        # От себя продавец видит модуль организации, открытый ему.
        self.seller.coop_acting_as_id = False
        mine = Conn.with_user(self.seller).action_coop_open_access()
        self.assertTrue(mine['context']['coop_access_person'])
        self.assertIn(rows, Conn.with_user(self.seller).search(mine['domain']))

    def test_no_crm_in_person_menu(self):
        if 'crm.lead' not in self.env:
            self.skipTest('нет crm')
        self.assertNotIn('CRM', self._ext_labels(self.seller))
