# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMenuTwins(TransactionCase):
    """Решение 493: штатные двойники — внутри наших разделов, права целы."""

    def test_twins_merged_and_technical_stays_admin_only(self):
        self.env['coop.menu.order'].apply()
        settings = self.env.ref('coop_settings.menu_coop_settings_root', raise_if_not_found=False)
        admin_root = self.env.ref('base.menu_administration')
        if not settings:
            self.skipTest('coop_settings не установлен')
        self.assertFalse(admin_root.active)
        technical = self.env.ref('base.menu_custom')
        self.assertEqual(technical.parent_id, settings)
        user = self.env['res.users'].create({
            'name': 'Участник проверки меню', 'login': 'menu-twins-user',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        Menu = self.env['ir.ui.menu'].with_user(user)
        for debug in (False, True):
            visible = Menu._visible_menu_ids(debug)
            self.assertNotIn(technical.id, visible)
            self.assertNotIn(self.env.ref('base.menu_users').id, visible)
        self.assertIn(technical.id,
                      self.env['ir.ui.menu'].with_user(self.env.ref('base.user_admin'))
                      ._visible_menu_ids(True))
        for xmlid in ('stock.menu_stock_root', 'event.event_main_menu'):
            root = self.env.ref(xmlid, raise_if_not_found=False)
            if root:
                self.assertFalse(root.active, xmlid)
