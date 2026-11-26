# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestContract510(TransactionCase):
    """Решение 510: в вакансии — только трудовой договор, подряд — задачей."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Form = cls.env['coop.legal.form']
        Partner = cls.env['res.partner']
        cls.dao = Partner.create({
            'name': 'ДАО Проверки 510', 'is_company': True,
            'coop_legal_form_id': Form.search([('code', '=', 'dao')], limit=1).id})
        cls.coop = Partner.create({
            'name': 'Потребкооператив Проверки 510', 'is_company': True,
            'coop_legal_form_id': Form.search(
                [('is_cooperative', '=', True), ('code', 'not in', ('dao', 'platform', 'artel'))],
                limit=1).id})

    def _vacancy(self, partner, **values):
        return self.env['coop.vacancy'].create(dict({
            'name': 'Проверка 510', 'partner_id': partner.id,
            'employment': 'project', 'reward_kind': 'money',
            'pay_from': 50000}, **values))

    def test_razovaya_rabota_kooperativa_trudovoy(self):
        vacancy = self._vacancy(self.coop)
        self.assertEqual(vacancy.contract_kind, 'labour')
        self.assertEqual(vacancy.pay_method, 'rub')
        self.assertNotIn('civil', dict(vacancy._fields['contract_kind'].selection))

    def test_dao_za_dengi_ne_publikuet(self):
        with self.assertRaises(UserError):
            self._vacancy(self.dao, state='published')

    def test_dao_za_dolyu_vakansiya_proekta(self):
        vacancy = self._vacancy(self.dao, reward_kind='share', state='published')
        self.assertFalse(vacancy.contract_kind)
