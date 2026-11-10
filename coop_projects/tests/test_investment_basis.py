# -*- coding: utf-8 -*-
"""Основание «Инвестирование» — только организации в коммерческом проекте или ДАО (задача 387)."""
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestInvestmentBasis(TransactionCase):

    def _project(self, kind, company):
        partner = self.env['res.partner'].create(
            {'name': 'Инициатор', 'is_company': company})
        return self.env['coop.project'].create({
            'name': 'Проект', 'kind': kind, 'partner_id': partner.id,
            'contribution_basis': 'investment'})

    def test_organization_commercial_and_dao(self):
        self.assertEqual(self._project('commercial', True).contribution_basis, 'investment')
        self.assertEqual(self._project('dao', True).contribution_basis, 'investment')

    def test_person_refused(self):
        with self.assertRaises(ValidationError):
            self._project('commercial', False)

    def test_cooperative_and_nonprofit_refused(self):
        for kind in ('cooperative', 'nonprofit'):
            with self.assertRaises(ValidationError):
                self._project(kind, True)
