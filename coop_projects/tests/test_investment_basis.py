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

    def test_pozhertvovanie_ne_u_ooo(self):
        """Решение 665 п. 3: у ООО вместо пожертвования — «Поддержка»."""
        form = self.env['coop.legal.form'].search([('code', '=', 'ooo')], limit=1)
        if not form:
            self.skipTest('Справочника форм нет')
        org = self.env['res.partner'].create({
            'name': 'ООО «Без пожертвований»', 'is_company': True,
            'coop_legal_form_id': form.id})
        project = self.env['coop.project'].create({
            'name': 'Проект ООО', 'kind': 'nonprofit', 'partner_id': org.id})
        self.assertEqual(project.contribution_basis, 'prepay')
        with self.assertRaises(ValidationError):
            project.contribution_basis = 'donation'
            project.flush_recordset()
        person = self.env['res.partner'].create({'name': 'Человек'})
        own = self.env['coop.project'].create({
            'name': 'Проект человека', 'kind': 'nonprofit',
            'partner_id': person.id})
        self.assertEqual(own.contribution_basis, 'donation')
