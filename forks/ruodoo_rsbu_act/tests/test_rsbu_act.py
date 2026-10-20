# -*- coding: utf-8 -*-
"""Акт сверки взаиморасчётов: сбор данных, XML (XSD), DOCX."""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRsbuAct(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # ИНН и КПП в пуле — coop_inn / coop_kpp (каталог организаций).
        pool = 'coop_inn' in cls.env['res.partner']._fields
        inn, kpp = ('coop_inn', 'coop_kpp') if pool else ('inn', 'kpp')
        cls.company.partner_id.write({
            inn: '5050164162', kpp: '505001001',
            'ogrn': '1234567890123'})
        user = cls.env['res.users'].search([], limit=1)
        user.partner_id.write({'name': 'Коробков Сергей Васильевич',
                               'function': 'Генеральный директор'})
        cls.company.rsbu_signatory_id = user.id
        cls.partner = cls.env['res.partner'].create({
            'name': 'ООО Контрагент', inn: '7701234567',
            kpp: '770101001', 'ogrn': '1027700132195'})

        # Счета своей компании: в пуле планов по числу организаций.
        A = cls.env['rsbu.account']
        own = [('company_id', '=', cls.company.id)]
        cls.acc62 = (A.search(own + [('code', '=', '62.01')], limit=1)
                     or A.search(own + [('code', '=', '62')], limit=1))
        cls.acc_other = A.search(own + [('is_group', '=', False),
                                        ('subconto_partner', '=', False)], limit=1)
        cls.Move = cls.env['rsbu.move']
        cls.Act = cls.env['ruodoo.rsbu.act']

    def _post(self, date, ref, acc_dr, acc_cr, amount, partner_side):
        """Создать и провести сбалансированную проводку.

        partner_side: 'dr' — партнёр на дебете acc_dr, 'cr' — на кредите acc_cr.
        """
        dr = {'account_id': acc_dr.id, 'debit': amount, 'name': ref}
        cr = {'account_id': acc_cr.id, 'credit': amount, 'name': ref}
        if partner_side == 'dr':
            dr['partner_id'] = self.partner.id
        else:
            cr['partner_id'] = self.partner.id
        move = self.Move.create({
            'date': date, 'company_id': self.company.id, 'ref': ref,
            'line_ids': [(0, 0, dr), (0, 0, cr)]})
        move.action_post()
        return move

    def _make_act(self):
        # Реализация Дт62—Кт(прочий) 100000; оплата Дт(прочий)—Кт62 60000.
        self._post('2026-03-10', 'Реализация', self.acc62, self.acc_other,
                   100000, 'dr')
        self._post('2026-03-20', 'Оплата', self.acc_other, self.acc62,
                   60000, 'cr')
        act = self.Act.create({
            'company_id': self.company.id, 'partner_id': self.partner.id,
            'date_from': '2026-01-01', 'date_to': '2026-12-31'})
        act.action_compute()
        return act

    def test_01_compute_balances(self):
        act = self._make_act()
        self.assertEqual(act.state, 'computed')
        self.assertEqual(len(act.line_ids), 2)
        self.assertAlmostEqual(act.turnover_debit, 100000.0, 2)
        self.assertAlmostEqual(act.turnover_credit, 60000.0, 2)
        # Дебетовое конечное сальдо (контрагент должен нам) = 40000.
        self.assertAlmostEqual(act.closing_debit, 40000.0, 2)
        self.assertAlmostEqual(act.closing_credit, 0.0, 2)

    def test_02_xml_valid_against_xsd(self):
        act = self._make_act()
        xml = act._act_build_xml()
        ok, errors = act._act_validate_xml(xml)
        self.assertTrue(ok, 'Акт не прошёл XSD: %s' % '; '.join(errors[:5]))
        self.assertIn(b'windows-1251', xml[:60])
        self.assertIn('1110332'.encode('cp1251'), xml)

    def test_03_docx_renders(self):
        act = self._make_act()
        tmpl = self.env.ref('ruodoo_rsbu_act.docx_template_act')
        content, ext = tmpl.report_id._render_docx_docx(res_ids=[act.id])
        self.assertEqual(ext, 'docx')
        self.assertTrue(len(content) > 10000)

    def test_04_opening_balance(self):
        """Сальдо прошлого периода попадает в начальное."""
        self._post('2025-12-15', 'Прошлая отгрузка', self.acc62,
                   self.acc_other, 30000, 'dr')
        act = self.Act.create({
            'company_id': self.company.id, 'partner_id': self.partner.id,
            'date_from': '2026-01-01', 'date_to': '2026-12-31'})
        act.action_compute()
        self.assertAlmostEqual(act.opening_debit, 30000.0, 2)


    def test_pool_act_numbering_per_company(self):
        other = self.env['res.company'].create({'name': 'Акт Вторая организация'})
        first = self.Act.create({'company_id': other.id, 'partner_id': self.partner.id})
        second = self.Act.create({'company_id': other.id, 'partner_id': self.partner.id})
        self.assertTrue(first.name.startswith('АС/'), first.name)
        self.assertTrue(first.name.endswith('00001'), first.name)
        self.assertTrue(second.name.endswith('00002'), second.name)
