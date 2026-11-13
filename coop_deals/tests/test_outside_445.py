# -*- coding: utf-8 -*-
"""«Без вступления» в окне «Участвовать» (задача 445, кусок 2; решение 679)."""
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.coop_projects.tests.common import CoopProjectCase


@tagged('post_install', '-at_install')
class TestOutside445(CoopProjectCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stranger = cls._make_person('Нечлен Без Вступления')

    def _project(self, form_code):
        org = self._make_org('Кооператив %s 445' % form_code)
        org.coop_legal_form_id = self.env['coop.legal.form'].search(
            [('code', '=', form_code)], limit=1)
        return self._make_project(partner=org, state='gathering')

    def _wizard(self, project):
        Wizard = self.env['coop.project.contribute'].with_user(self.stranger)
        wizard = Wizard.create({
            'project_id': project.id, 'path': 'outside',
            'name': '-', 'value': 0})
        return wizard

    def test_tsepochka_po_umolchaniyu(self):
        """Окно сразу показывает вид, договор и оплату — не пустые радио."""
        wizard = self._wizard(self._project('pk'))
        self.assertTrue(wizard.deal_kind_id)
        self.assertEqual(wizard.deal_way_id.kind_id, wizard.deal_kind_id)
        self.assertIn(wizard.deal_pay_id, wizard.deal_way_id.pay_ids)
        wizard.deal_kind_id = self.env.ref('coop_deals.contribute_kind_knowledge')
        self.assertEqual(wizard.deal_way_id.deal_way, 'license')

    def test_zaima_net_nigde(self):
        """679 п. 1: участие в проекте — не заём."""
        ways = self.env['coop.contribute.way'].search([])
        self.assertTrue(ways)
        self.assertNotIn('loan', ways.mapped('deal_way'))

    def test_dengi_skryty_po_forme(self):
        for code in ('kpk', 'skpk', 'zhsk', 'gsk'):
            wizard = self._wizard(self._project(code))
            self.assertNotIn('money', wizard.deal_kind_ids.mapped('code'), code)
            self.assertTrue(wizard.deal_money_closed, code)
        wizard = self._wizard(self._project('po'))
        self.assertIn('money', wizard.deal_kind_ids.mapped('code'))
        self.assertFalse(wizard.deal_money_closed)

    def test_sdelka_po_dogovoru(self):
        project = self._project('pk')
        wizard = self._wizard(project)
        kind = self.env.ref('coop_deals.contribute_kind_material')
        way = self.env.ref('coop_deals.contribute_way_material_exchange')
        wizard.deal_kind_id = kind
        wizard.deal_way_id = way
        self.assertEqual(wizard.deal_pay_id.code, 'product')
        wizard.write({'deal_name': 'Доски обрезные, 3 куба',
                      'deal_amount': 45000})
        action = wizard.action_coop_propose_deal()
        deal = self.env['coop.deal'].sudo().browse(action['res_id'])
        self.assertEqual(deal.way, 'exchange')
        self.assertEqual(deal.state, 'lead')
        self.assertEqual(deal.party_b_id, project.partner_id)

    def test_chuzhoi_dogovor_i_skrytyi_vid_ne_proidut(self):
        wizard = self._wizard(self._project('kpk'))
        wizard.deal_name = 'Пожертвование'
        wizard.deal_kind_id = self.env.ref('coop_deals.contribute_kind_money')
        wizard.deal_way_id = self.env.ref('coop_deals.contribute_way_money_gift')
        with self.assertRaises(UserError):
            wizard.action_coop_propose_deal()
        wizard.deal_kind_id = self.env.ref('coop_deals.contribute_kind_space')
        wizard.deal_way_id = self.env.ref('coop_deals.contribute_way_knowledge_gift')
        with self.assertRaises(UserError):
            wizard.action_coop_propose_deal()

    def test_trud_s_preduprezhdeniem(self):
        wizard = self._wizard(self._project('pk'))
        wizard.deal_kind_id = self.env.ref('coop_deals.contribute_kind_labour')
        self.assertIn('Работать', wizard.deal_kind_warning)
