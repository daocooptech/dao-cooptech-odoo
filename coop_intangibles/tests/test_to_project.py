# -*- coding: utf-8 -*-
"""Нематериальный актив участвует в проектах (№ 395, слово владельца 10.11)."""
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.coop_projects.tests.common import CoopProjectCase


@tagged('post_install', '-at_install')
class TestIntangibleToProject(CoopProjectCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.org = cls._make_org('Правообладатель проектов')
        cls.other_org = cls._make_org('Инициатор для актива')
        cls.project = cls._make_project('Проект с активом', partner=cls.other_org,
                                        state='gathering')
        cls.asset = cls.env['coop.intangible'].create({
            'name': 'Рецептура сыра', 'owner_id': cls.org.id, 'kind': 'know_how',
            'state': 'active', 'initial_cost': 200000,
            'legal_basis': 'Приказ о режиме коммерческой тайны № 7',
        })

    def _offer(self, **values):
        wizard = self.env['coop.intangible.to.project'].create(dict({
            'intangible_id': self.asset.id, 'project_id': self.project.id,
            'value': 150000,
        }, **values))
        return wizard.action_offer()

    def test_vnesti_s_kartochki_aktiva(self):
        self._offer(ownership_kind='use')
        offer = self.asset.contribution_ids
        self.assertEqual(len(offer), 1)
        self.assertEqual((offer.project_id, offer.intangible_id, offer.state),
                         (self.project, self.asset, 'offered'))
        self.assertEqual(offer.ownership_kind, 'use')
        self.assertEqual(self.asset.project_offer_count, 1)

    def test_tolko_dejstvuyushchee_pravo(self):
        self.asset.state = 'draft'
        with self.assertRaises(UserError):
            self._offer()

    def test_svoj_proekt_ne_v_spiske(self):
        own = self._make_project('Свой проект правообладателя', partner=self.org,
                                 state='gathering')
        wizard = self.env['coop.intangible.to.project'].create({
            'intangible_id': self.asset.id, 'project_id': self.project.id, 'value': 1})
        self.assertNotIn(own, wizard.project_ids)
        self.assertIn(self.project, wizard.project_ids)

    def test_schetchik_organizacii(self):
        self.assertEqual(self.org.coop_asset_project_count, 0)
        self._offer()
        self.env.invalidate_all()
        self.assertEqual(self.org.coop_asset_project_count, 1)
        action = self.org.action_coop_assets_in_projects()
        self.assertEqual(action['res_model'], 'coop.project.contribution')

    def test_zakryvaet_potrebnost_na_etot_aktiv(self):
        need = self.env['coop.intangible.need'].create({
            'project_id': self.project.id, 'intangible_id': self.asset.id, 'price': 150000})
        self._offer()
        offer = self.asset.contribution_ids
        self.assertEqual(offer.need_intangible_id, need)

    def test_uchastvovat_vidom_nma_s_poiskom_po_nazvaniyu(self):
        """В обычном «Участвовать» — вид «Нематериальный актив» и выбор из своих
        действующих активов (поиск по началу названия — штатный поиск поля)."""
        user = self.initiator
        mine = user.partner_id
        asset = self.env['coop.intangible'].create({
            'name': 'Программа учёта смен', 'owner_id': mine.id, 'kind': 'software',
            'state': 'active', 'initial_cost': 80000,
            'legal_basis': 'Свидетельство о регистрации программы № 1',
        })
        draft = self.env['coop.intangible'].create({
            'name': 'Программа в черновике', 'owner_id': mine.id, 'kind': 'software',
            'legal_basis': 'Свидетельство о регистрации программы № 2',
        })
        wizard = self.env['coop.project.contribute'].with_user(user).create({
            'project_id': self.project.id, 'kind': 'intangible', 'name': 'x', 'value': 50000,
            'intangible_id': asset.id})
        self.assertIn(asset, wizard.my_intangible_ids)
        self.assertNotIn(draft, wizard.my_intangible_ids)
        found = self.env['coop.intangible'].search(
            [('id', 'in', wizard.my_intangible_ids.ids), ('name', 'ilike', 'Программа у')])
        self.assertEqual(found, asset)
        wizard.action_offer()
        offer = asset.contribution_ids
        self.assertEqual((offer.kind, offer.return_mode), ('intangible', 'compensation'))

