# -*- coding: utf-8 -*-
"""Граждане КНР принимаются все, с предупреждением о SAFE (решение 503)."""
from odoo.tests import tagged

from odoo.addons.coop_base.tests.common import CoopCase


@tagged('post_install', '-at_install')
class TestSafeNotice(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.coop = cls._make_org('Потребительское общество пробы')
        cls.coop.coop_legal_form_id = cls.env['coop.legal.form'].search(
            [('code', '=', 'po')], limit=1)
        cls.chinese = cls._make_person('Гражданин КНР в Шанхае')
        cls.chinese.partner_id.write({
            'coop_citizenship_id': cls.env.ref('base.cn').id,
            'country_id': cls.env.ref('base.cn').id})
        cls.russian = cls._make_person('Гражданин РФ в Шанхае')
        cls.russian.partner_id.write({
            'coop_citizenship_id': cls.env.ref('base.ru').id,
            'country_id': cls.env.ref('base.cn').id})

    def _wizard(self, user):
        return self.env['coop.org.join'].with_user(user).create(
            {'organization_id': self.coop.id})

    def test_grazhdaninu_knr_preduprezhdenie(self):
        wizard = self._wizard(self.chinese)
        self.assertEqual(wizard.role_id.code, 'member')
        self.assertTrue(wizard.safe_notice)

    def test_rossiyaninu_v_kitae_net(self):
        self.assertFalse(self._wizard(self.russian).safe_notice)
