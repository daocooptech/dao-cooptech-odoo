# -*- coding: utf-8 -*-
"""Форма собственности и налоговый режим — двумя полями (№ 447)."""
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFormRegime(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env['coop.economic.loader'].load_forms()
        Model = self.env['coop.economic.model']
        self.ooo = Model.search([('key', '=', 'ooo_usn_income')])
        self.pao = Model.search([('key', '=', 'ao_public_osno')])

    def test_names_split(self):
        models = self.env['coop.economic.model'].search([('form_id', '!=', False)])
        self.assertEqual(self.ooo.form_id.name, 'ООО')
        for form in models.form_id:
            self.assertNotRegex(form.name, r'УСН|ЕСХН|ОСНО|НПД|ПСН|патент')
        self.assertEqual(
            self.ooo.with_context(coop_regime_only=True).display_name, 'УСН «доходы»')
        self.assertEqual(self.ooo.display_name, 'ООО на УСН «доходы»')

    def test_project_form_follows_regime(self):
        project = self.env['coop.project'].new({'economic_model_id': self.ooo.id})
        self.assertEqual(project.economic_form_id, self.ooo.form_id)
        project.economic_form_id = self.pao.form_id
        project._onchange_economic_form_id()
        self.assertEqual(project.economic_model_id, self.pao)
        project.economic_form_id = self.ooo.form_id
        project._onchange_economic_form_id()
        self.assertFalse(project.economic_model_id)
        self.assertEqual(project.economic_form_id, self.ooo.form_id)

    def test_foreign_regime_refused(self):
        project = self.env['coop.project'].search(
            [('economic_model_id', '!=', False)], limit=1)
        if not project:
            self.skipTest('нет проектов')
        project.economic_model_id = self.ooo
        self.assertEqual(project.economic_form_id, self.ooo.form_id)
        with self.assertRaises(ValidationError):
            project.economic_form_id = self.pao.form_id
            project.flush_recordset()
