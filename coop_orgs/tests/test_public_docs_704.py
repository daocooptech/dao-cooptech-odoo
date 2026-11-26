# -*- coding: utf-8 -*-
"""Публичные документы организации — в «Документах» (решение 704)."""
import base64

from odoo.tests import tagged

from odoo.addons.coop_base.tests.common import CoopCase


@tagged('post_install', '-at_install')
class TestPublicDocs704(CoopCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.org = cls._make_org('Артель 704')
        cls.stranger = cls._make_person('Чужой 704')
        cls.doc = cls.org._coop_put_public_doc(
            'charter', 'Устав, ред. 2024', base64.b64encode(b'%PDF-1.4 704'), 'charter.pdf')

    def test_v_dokumentakh_i_v_kartochke(self):
        self.assertEqual(self.org.coop_charter_doc_id, self.doc)
        self.assertEqual((self.doc.kind, self.doc.party_a_id, self.doc.is_public, self.doc.state),
                         ('charter', self.org, True, 'signed'))
        self.assertTrue(self.doc.fingerprint)

    def test_chuzhoi_chitaet_no_ne_v_svoem_razdele(self):
        Doc = self.env['coop.document'].with_user(self.stranger)
        self.assertEqual(Doc.browse(self.doc.id).name, 'Устав, ред. 2024')
        action = self.env.ref('coop_documents.action_coop_documents')
        from odoo.tools.safe_eval import safe_eval
        self.assertNotIn(self.doc, Doc.search(safe_eval(action.domain)))
