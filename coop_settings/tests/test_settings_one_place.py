# -*- coding: utf-8 -*-
"""Настройки — в одном месте (№ 302): окно движка ведёт в «Аккаунт»,
ключи API и ключи доступа — во вкладке «Безопасность»."""
from odoo.tests import tagged

from odoo.addons.coop_base.tests.common import CoopCase


@tagged('post_install', '-at_install')
class TestSettingsOnePlace(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.person = cls._make_person('Участник проверки настроек')
        cls.account_view = cls.env.ref(
            'coop_settings.view_coop_settings_account_form')

    def _assert_account(self, action):
        self.assertEqual(action['res_model'], 'res.partner')
        self.assertEqual(action['res_id'], self.person.partner_id.id)
        self.assertEqual(action['views'][0][0], self.account_view.id)
        self.assertEqual(action['target'], 'current')

    def test_okno_dvizhka_iz_menyu(self):
        self._assert_account(
            self.env['res.users'].with_user(self.person).action_get())

    def test_okno_dvizhka_po_ssylke(self):
        act = self.env.ref('base.action_res_users_my')
        self._assert_account(
            act.with_user(self.person).sudo()._get_action_dict())

    def test_drugie_okna_ne_tronuty(self):
        act = self.env.ref('base.action_res_users')
        self.assertEqual(act.sudo()._get_action_dict()['res_model'], 'res.users')

    def test_klyuchi_vo_vkladke_bezopasnost(self):
        arch = self.env['res.users'].with_user(self.person).get_views(
            [(self.env.ref('coop_settings.view_coop_settings_security_form').id,
              'form')])['views']['form']['arch']
        for name in ('api_key_ids', 'api_key_wizard',
                     'auth_passkey_key_ids', 'action_create_passkey'):
            self.assertIn(name, arch)

    def test_zagolovki_masterov_po_russki(self):
        # Оба мастера движок открывает только из браузера, после проверки
        # пароля по HTTP, — здесь только то, что методы переопределены.
        for model, name in (('res.users', 'api_key_wizard'),
                            ('res.users', 'action_create_passkey'),
                            ('res.users.apikeys.description', 'make_key')):
            method = getattr(type(self.env[model]), name)
            self.assertIn('coop_settings', method.__module__)
            # Без пометки движок после ввода пароля метод не вызовет.
            self.assertTrue(getattr(method, '__has_check_identity', False))

    def test_sroki_klyucha_po_russki(self):
        labels = dict(self.env['res.users.apikeys.description']
                      .with_user(self.person)._selection_duration())
        self.assertEqual(labels.get('1'), 'Сутки')
