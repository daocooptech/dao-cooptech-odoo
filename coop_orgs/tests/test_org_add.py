# -*- coding: utf-8 -*-
"""Страница «Добавить организацию» (№ 377, `OrgAddPage`)."""
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.coop_base.tests.common import CoopCase

from ..models.coop_org_add import inn_is_valid


@tagged('post_install', '-at_install')
class TestOrgAdd(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.person = cls._make_person('Создатель Организации')
        cls._confirm(cls.person.partner_id, 'phone')
        cls.form = cls.env['coop.legal.form'].search([('code', '=', 'pk')], limit=1)

    def _page(self, **values):
        return self.env['coop.org.add'].with_user(self.person).create(dict({
            'name': 'ПК «Проверка»', 'group_code': 'cooperative',
            'form_id': self.form.id}, **values))

    def test_inn(self):
        self.assertTrue(inn_is_valid('7707083893'))
        self.assertTrue(inn_is_valid('500100732259'))
        for bad in ('7707083894', '123', 'абвгдежзик', '500100732258'):
            self.assertFalse(inn_is_valid(bad), bad)

    def test_create(self):
        """Создавший — уполномоченный, организация в каталоге."""
        self.env['res.partner'].with_user(self.person).action_coop_new_org()
        action = self._page(city='Тула').action_create_org()
        org = self.env['res.partner'].browse(action['res_id'])
        self.assertTrue(org.is_company and org.coop_is_participant)
        self.assertTrue(org.coop_is_cooperative)
        member = org.coop_member_ids
        self.assertEqual(member.partner_id, self.person.partner_id)
        self.assertEqual((member.role, member.state), ('founder', 'active'))
        self.assertTrue(self.person.coop_has_power('publish', org))
        self.assertTrue(org.with_user(self.person).coop_can_edit_card)

    def test_refusals(self):
        for values in ({'name': False}, {'form_id': False}, {'inn': '7707083894'},
                       {'group_code': 'commercial'}):
            with self.assertRaises(UserError):
                self._page(**values).action_create_org()
        org = self._make_org('Занятый ИНН')
        org.write({'coop_inn': '7707083893', 'coop_is_participant': True})
        with self.assertRaises(UserError):
            self._page(inn='7707083893').action_create_org()

    def test_no_contact_level(self):
        stranger = self._make_person('Без Телефона')
        page = self.env['coop.org.add'].with_user(stranger).create({
            'name': 'ПК «Нет»', 'group_code': 'cooperative', 'form_id': self.form.id})
        with self.assertRaises(UserError):
            page.action_create_org()

    def test_found(self):
        page = self._page(name=False, form_id=False, group_code='commercial')
        page._coop_apply_found({
            'name': 'ПК "РОДНИК"', 'kpp': '770701001', 'ogrn': '1027700132195',
            'arceat': '01.13', 'city': 'Тула'})
        self.assertEqual(page.form_id, self.form)
        self.assertEqual(page.group_code, 'cooperative')
        self.assertEqual(page.okved_id.code, '01')
