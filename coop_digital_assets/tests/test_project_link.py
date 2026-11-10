# -*- coding: utf-8 -*-
"""Выпуск ЦФА под проект и вкладка «ЦФА» в аналитике (№ 395)."""
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.coop_projects.tests.common import CoopProjectCase


@tagged('post_install', '-at_install')
class TestCfaProjectLink(CoopProjectCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.org = cls._make_org('Эмитент проекта')
        cls.project = cls._make_project('Проект под выпуск', partner=cls.org)
        cls.Issue = cls.env['coop.cfa.issue']

    def _issue(self, **values):
        return self.Issue.create(dict({
            'issuer_id': self.org.id, 'name': 'Выпуск под проект',
            'amount': 1000000, 'unit_count': 1000, 'state': 'issued',
        }, **values))

    def test_vypusk_pod_svoj_proekt(self):
        issue = self._issue(project_id=self.project.id)
        self.assertEqual(self.project.cfa_issue_ids, issue)
        self.assertEqual(self.project.cfa_issue_count, 1)

    def test_chuzhoj_proekt_nelzya(self):
        other = self._make_org('Другая организация')
        with self.assertRaises(ValidationError):
            self._issue(issuer_id=other.id, project_id=self.project.id)

    def test_chernovik_ne_schitaetsya(self):
        self._issue(project_id=self.project.id, state='draft')
        self.assertEqual(self.project.cfa_issue_count, 0)
        self.assertEqual(self.org.coop_cfa_count, 0)

    def test_razmeshcheno_po_vladeniyam(self):
        issue = self._issue(project_id=self.project.id)
        holder = self.env['res.partner'].create({'name': 'Владелец ЦФА'})
        self.env['coop.cfa.holding'].create({
            'partner_id': holder.id, 'operator_id': issue.operator_id.id,
            'issue_id': issue.id, 'name': issue.name, 'quantity': 250})
        html = str(self.project.analytics_cfa)
        self.assertIn('250 000', html)        # 250 из 1000 единиц по 1000 ₽
        self.assertIn('Выпуск под проект', html)

    def test_pusto_bez_vypuskov(self):
        self.assertIn('Выпусков ЦФА под этот проект нет', str(self.project.analytics_cfa))

    def test_schetchik_organizacii(self):
        self._issue(project_id=self.project.id)
        self.assertEqual(self.org.coop_cfa_count, 1)
        action = self.org.action_coop_cfa_issues()
        self.assertEqual(action['res_model'], 'coop.cfa.issue')
