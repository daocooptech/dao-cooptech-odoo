# -*- coding: utf-8 -*-
"""Основа кооперативных выплат — поле устава (решение 511)."""
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.coop_base.tests.common import CoopCase


@tagged('post_install', '-at_install')
class TestPayoutBasis511(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Form = cls.env['coop.legal.form']
        cls.po = cls._make_org('Потребобщество 511')
        cls.po.coop_legal_form_id = Form.search([('code', '=', 'po')], limit=1)
        cls.artel = cls._make_org('Артель 511')
        cls.artel.coop_legal_form_id = Form.search([('code', '=', 'artel')], limit=1)
        cls.plain = cls._make_org('Сообщество 511')

    def test_po_po_oborotu_artel_po_trudu(self):
        self.assertEqual(self.po.coop_payout_basis, 'turnover')
        self.assertEqual(self.artel.coop_payout_basis, 'labor')
        self.assertFalse(self.plain.coop_payout_basis)

    def test_po_trudu_tolko_artel(self):
        with self.assertRaises(ValidationError):
            self.po.coop_payout_basis = 'labor'
            self.po.flush_recordset()
        with self.assertRaises(ValidationError):
            self.artel.coop_payout_basis = 'turnover'
            self.artel.flush_recordset()

    def test_smena_formy_menyaet_osnovu(self):
        self.po.coop_legal_form_id = self.env['coop.legal.form'].search(
            [('code', '=', 'artel')], limit=1)
        self.assertEqual(self.po.coop_payout_basis, 'labor')
