# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResourceProcess(TransactionCase):
    """Технологический процесс на витрине ресурса (решение 630)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env['res.partner']
        cls.org = Partner.create({'name': 'ПК «Пасека Проба»', 'is_company': True})
        cls.org.coop_app_mrp = True
        cls.head = cls._member('Председатель Пасеки', ['sign', 'represent'])
        cls.keeper = cls._member('Пасечник Пробы', ['deal'])
        cls.org._coop_ensure_company()
        cls.env['res.users']._coop_sync_accounting_access(cls.org)
        cls.buyer = cls.env['res.users'].create({
            'name': 'Покупатель Мёда', 'login': 'pokupatel-meda-mrp',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        company = cls.org.coop_company_id
        Center = cls.env['mrp.workcenter'].with_company(company)
        apiary = Center.create({'name': 'Пасека', 'company_id': company.id})
        room = Center.create({'name': 'Медогонная', 'company_id': company.id})
        product = cls.env['product.product'].create({'name': 'Мёд липовый', 'company_id': company.id})
        cls.bom = cls.env['mrp.bom'].with_company(company).create({
            'product_tmpl_id': product.product_tmpl_id.id, 'company_id': company.id,
            'product_qty': 1,
            'operation_ids': [
                (0, 0, {'name': 'Осмотр ульев', 'workcenter_id': apiary.id, 'sequence': 1,
                        'time_cycle_manual': 20, 'coop_instruction': '<p>Дымарь, сетка.</p>'}),
                (0, 0, {'name': 'Отбор рамок', 'workcenter_id': apiary.id, 'sequence': 2,
                        'time_cycle_manual': 20}),
                (0, 0, {'name': 'Откачка', 'workcenter_id': room.id, 'sequence': 3,
                        'time_cycle_manual': 90}),
            ],
        })
        cls.listing = cls.env['coop.resource'].create({
            'name': 'Мёд липовый', 'listing_type': 'offer',
            'owner_id': cls.org.id, 'bom_id': cls.bom.id,
        })

    @classmethod
    def _member(cls, name, codes):
        user = cls.env['res.users'].create({
            'name': name, 'login': name.replace(' ', '-').lower(),
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.env['coop.membership'].create({
            'partner_id': user.partner_id.id,
            'organization_id': cls.org.id,
            'state': 'active',
            'admission_basis': 'Решение правления № 1',
            'power_ids': [(6, 0, cls.env['coop.power'].search([('code', 'in', codes)]).ids)],
        })
        return user

    def test_app_opens_production(self):
        self.assertTrue(self.keeper.has_group('mrp.group_mrp_manager'))
        self.assertFalse(self.buyer.has_group('mrp.group_mrp_user'))
        self.org.coop_app_mrp = False
        self.assertFalse(self.keeper.has_group('mrp.group_mrp_manager'))

    def test_hidden_until_org_shows(self):
        listing = self.listing.with_user(self.buyer)
        self.assertFalse(listing.process_steps)
        # Показ включает руководитель, а не любой член организации.
        with self.assertRaises(UserError):
            self.org.with_user(self.keeper).coop_show_process = True
        self.org.with_user(self.head).coop_show_process = True
        self.listing.invalidate_recordset()
        steps = listing.process_steps
        self.assertEqual([s['title'] for s in steps], ['Пасека', 'Медогонная'])
        self.assertEqual(steps[0]['duration'], '40 мин')
        self.assertEqual(steps[1]['duration'], '1 ч 30 мин')
        self.assertEqual([c['title'] for c in steps[0]['children']], ['Осмотр ульев', 'Отбор рамок'])
        self.assertEqual([l['kind'] for l in steps[0]['children'][0]['links']], ['instruction'])
        self.assertEqual(listing.process_caption, '2 этапа · 2 ч 10 мин')

    def test_doc_only_for_shown_operation(self):
        self.org.coop_show_process = True
        op = self.bom.operation_ids[0]
        doc = self.listing.with_user(self.buyer).coop_process_doc(op.id, 'instruction')
        self.assertIn('Дымарь', doc['body'])
        other = self.env['mrp.routing.workcenter'].search([('id', 'not in', self.bom.operation_ids.ids)], limit=1)
        if other:
            with self.assertRaises(UserError):
                self.listing.with_user(self.buyer).coop_process_doc(other.id, 'instruction')
        # Результата нет, пока партия не выпущена.
        with self.assertRaises(UserError):
            self.listing.with_user(self.buyer).coop_process_doc(op.id, 'result')

    def test_batch_gives_caption_and_results(self):
        self.org.coop_show_process = True
        company = self.org.coop_company_id
        production = self.env['mrp.production'].with_company(company).create({
            'product_id': self.bom.product_tmpl_id.product_variant_id.id,
            'bom_id': self.bom.id, 'product_qty': 50, 'company_id': company.id,
        })
        production.action_confirm()
        production.qty_producing = 50
        for wo in production.workorder_ids:
            wo.button_start()
            wo.button_finish()
        production.button_mark_done()
        self.assertEqual(production.state, 'done')
        self.listing.invalidate_recordset()
        listing = self.listing.with_user(self.buyer)
        self.assertTrue(listing.process_caption.startswith('Партия № %s от ' % production.name))
        links = listing.process_steps[1]['children'][0]['links']
        self.assertEqual([l['kind'] for l in links], ['result'])
        doc = listing.coop_process_doc(links[0]['op'], 'result')
        self.assertIn(production.name, doc['body'])
