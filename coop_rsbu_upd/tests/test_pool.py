"""Правки пула к УПД слоя (К6, задача 294)."""
from odoo.addons.coop_invoicing.models.upd_legacy import ARCHIVE_NOTE
from odoo.addons.coop_rsbu_upd.hooks import post_init_move_upd_requisites
from odoo.tests import tagged

from .test_upd_xml import TestUpdXml


@tagged('post_install', '-at_install')
class TestUpdPool(TestUpdXml):

    def test_pool_vat_22_passes_xsd_05_03_05(self):
        real = self._realization(self._source_move(qty=1, price=1000.0),
                                 vat_rate='vat_22')
        xml_bytes = real._upd_build_xml(filename='T22')
        self.assertIn('НалСт="22%"', xml_bytes.decode('cp1251'))
        ok, errors = real._upd_validate_xml(xml_bytes)
        self.assertTrue(ok, '; '.join(errors[:5]))

    def test_pool_filename_is_constant(self):
        real = self._realization(self._source_move())
        name = real._upd_filename()
        self.assertEqual(name, real._upd_filename())
        self.assertIn('_20260630_', name)
        other = self._realization(self._source_move())
        self.assertNotEqual(name, other._upd_filename())

    def test_pool_archived_filename_is_kept(self):
        move = self._source_move()
        self.env['ir.attachment'].create({
            'name': 'ON_NSCHFDOPPR_OLD_1.xml', 'res_model': 'account.move',
            'res_id': move.id, 'raw': b'<x/>', 'description': ARCHIVE_NOTE})
        real = self._realization(move)
        self.assertEqual(real._upd_filename(), 'ON_NSCHFDOPPR_OLD_1')

    def test_pool_requisites_moved_from_legacy_fields(self):
        company = self.company
        if 'edi' not in company._fields:
            self.skipTest('нет l10n_ru_upd_xml')
        company.write({'rsbu_edo_participant_id': False, 'rsbu_edo_operator_code': '000'})
        company.write({'edi': 'EDI-OLD-1', 'edi_operator': '2BE'})
        self.buyer.write({'edi': 'EDI-BUYER-1', 'rsbu_edo_participant_id': False})
        post_init_move_upd_requisites(self.env)
        self.assertEqual(company.rsbu_edo_participant_id, 'EDI-OLD-1')
        self.assertEqual(company.rsbu_edo_operator_code, '2BE')
        self.assertEqual(self.buyer.rsbu_edo_participant_id, 'EDI-BUYER-1')

    def test_pool_treasury_gets_rsbu_group_when_enabled(self):
        org = self.env['res.partner'].create({'name': 'ПК «Слой»', 'is_company': True})
        user = self.env['res.users'].create({
            'name': 'Казначей Слоя', 'login': 'kaznachei-sloya',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.env['coop.membership'].create({
            'partner_id': user.partner_id.id, 'organization_id': org.id,
            'state': 'active', 'admission_basis': 'Решение правления № 1',
            'power_ids': [(6, 0, self.env['coop.power'].search(
                [('code', '=', 'treasury')]).ids)]})
        company = org._coop_ensure_company()
        group = self.env.ref('rsbu_journal.group_rsbu_journal_manager')
        self.assertNotIn(group, user.group_ids)
        company.rsbu_enabled = True
        self.assertIn(group, user.group_ids)
        self.assertIn(company, user.company_ids)
