# -*- coding: utf-8 -*-
"""Заявление пайщика в три шага (задача 445, решения 677–679)."""
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.coop_base.tests.common import CoopCase


@tagged('post_install', '-at_install')
class TestJoin445(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Form = cls.env['coop.legal.form']
        cls.po = cls._make_org('Потребобщество 445')
        cls.po.write({
            'coop_legal_form_id': Form.search([('code', '=', 'po')], limit=1).id,
            'coop_charter_url': 'https://po445.example/charter.pdf'})
        cls.spk = cls._make_org('Сельхозкооператив 445')
        cls.spk.write({
            'coop_legal_form_id': Form.search([('code', '=', 'spk')], limit=1).id,
            'coop_charter_url': 'https://spk445.example/charter.pdf'})
        cls.applicant = cls._make_person('Заявитель 445')

    def _wizard(self, org):
        return self.env['coop.org.join'].with_user(self.applicant).with_context(
            default_organization_id=org.id).create({'organization_id': org.id})

    def test_naemnogo_net_assotsiirovannyi_tolko_v_selkhoz(self):
        po_codes = set(self._wizard(self.po).allowed_role_ids.mapped('code'))
        spk_codes = set(self._wizard(self.spk).allowed_role_ids.mapped('code'))
        self.assertEqual(po_codes, {'member'})
        self.assertEqual(spk_codes, {'member', 'associate'})

    def test_bez_oznakomleniya_ne_podat(self):
        wizard = self._wizard(self.po)
        wizard.action_next()
        self.assertEqual(wizard.step, 'docs')
        with self.assertRaises(UserError):
            wizard.action_next()
        with self.assertRaises(UserError):
            wizard.action_apply()
        wizard.acknowledged = True
        wizard.action_next()
        self.assertEqual(wizard.step, 'apply')
        wizard.action_apply()
        membership = self.env['coop.membership'].sudo().search([
            ('partner_id', '=', self.applicant.partner_id.id),
            ('organization_id', '=', self.po.id)])
        self.assertEqual(membership.state, 'applied')
        self.assertTrue(membership.coop_acknowledged_on)
        self.assertEqual(self._wizard(self.po).block, 'applied')

    def test_bez_ustava_blok(self):
        org = self._make_org('Кооператив без устава 445')
        org.coop_legal_form_id = self.po.coop_legal_form_id
        wizard = self._wizard(org)
        self.assertEqual(wizard.block, 'no_charter')
        wizard.acknowledged = True
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_nabor_zakryt(self):
        org = self._make_org('Кооператив с закрытым набором 445')
        org.write({'coop_legal_form_id': self.po.coop_legal_form_id.id,
                   'coop_charter_url': 'https://x445.example/charter.pdf',
                   'coop_join_open': False,
                   'coop_join_closed_note': 'набор до марта'})
        wizard = self._wizard(org)
        self.assertEqual(wizard.block, 'closed')
        self.assertIn('набор до марта', wizard.block_note)
