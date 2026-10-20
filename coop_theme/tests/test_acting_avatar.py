# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestActingAvatar(HttpCase):
    """Аватар в шапке — того, от чьего имени действуешь (задача 299)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.org = cls.env['res.partner'].create(
            {'name': 'ПК «Проба аватара»', 'is_company': True})
        cls.user = cls.env['res.users'].create({
            'name': 'Участник Пробы аватара', 'login': 'proba-avatara',
            'password': 'proba-avatara',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.env['coop.membership'].create({
            'partner_id': cls.user.partner_id.id,
            'organization_id': cls.org.id,
            'state': 'active',
            'admission_basis': 'Решение правления № 1',
            # Без полномочий действовать от организации нечего — не даст.
            'power_ids': [(6, 0, cls.env['coop.power'].search([('code', '=', 'deal')]).ids)],
        })

    def _session_acting(self):
        return self.make_jsonrpc_request('/web/session/get_session_info')['coop_acting']

    def test_self_has_no_acting(self):
        """От себя — пусто, и веб-клиент открывается (20.10 падал с 500)."""
        self.authenticate('proba-avatara', 'proba-avatara')
        self.assertFalse(self._session_acting())
        self.assertEqual(self.url_open('/odoo').status_code, 200)

    def test_org_gives_its_avatar(self):
        """От организации — её номер и дата правки для картинки в шапке."""
        self.user.action_coop_act_as(self.org.id)
        self.authenticate('proba-avatara', 'proba-avatara')
        acting = self._session_acting()
        self.assertEqual(acting['id'], self.org.id)
        self.assertTrue(acting['write_date'])
        self.assertEqual(self.url_open('/odoo').status_code, 200)
