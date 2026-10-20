# -*- coding: utf-8 -*-
"""Приёмочные тесты рефакторинга «Документ реализации» (Stage 6).

Воплощают критерии владельца (вариант 1 из эталона 1С): документ реализации
создаётся для ЛЮБОЙ отгрузки; при наличии НДС хотя бы в одной строке он
порождает подчинённый отгрузочный счёт-фактуру; из реализации печатается и
выгружается УПД (Функция СЧФДОП при наличии СФ, иначе ДОП); авансовый СФ
по-прежнему рождается из платежа; книга продаж не зависит от наличия СФ.

Эти тесты требуют и rsbu_vat (модель rsbu.realization, книги), и
rsbu_fns_reporting (кнопка action_create_realization на инвойсе, XML/DOCX
на реализации) — обе части устанавливаются в прогоне свиты.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRealizationAcceptance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.rsbu_vat_mode = 'vat_5'
        # Реквизиты для прохождения _upd_validate (XML/XSD).
        cls.company.partner_id.write({
            'inn': '7704567896', 'kpp': '770401001',
            'city': 'Москва', 'street': 'ул. Тестовая, 1'})
        cls.user = cls.env['res.users'].search([], limit=1)
        cls.company.rsbu_signatory_id = cls.user.id
        cls.user.partner_id.function = 'Директор'
        cls.company.rsbu_edo_operator_code = '2BM'
        cls.company.rsbu_edo_participant_id = '2BM-SENDER-1'
        cls.buyer = cls.env['res.partner'].create({
            'name': 'ООО Покупатель', 'inn': '7730179829',
            'city': 'Москва', 'street': 'ул. Клиент, 2',
            'rsbu_edo_participant_id': '2BM-BUYER-1'})
        cls.product = cls.env['product.product'].create({
            'name': 'Услуга А', 'type': 'service'})
        cls.product.uom_id.okei = '796'
        cls.journal_bank = cls.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', cls.company.id)],
            limit=1)

    # -- helpers --------------------------------------------------------
    def _acc(self, code):
        return self.env['rsbu.account'].search([
            ('code', '=', code),
            ('company_id', '=', self.company.id)], limit=1)

    def _tax(self, amount=5.0):
        name = 'НДС %g%%' % amount
        tax = self.env['account.tax'].search([
            ('name', '=', name), ('type_tax_use', '=', 'sale'),
            ('company_id', '=', self.company.id)], limit=1)
        if not tax:
            tax = self.env['account.tax'].create({
                'name': name, 'amount': amount, 'amount_type': 'percent',
                'type_tax_use': 'sale', 'company_id': self.company.id})
        return tax

    def _shipment_matrix(self):
        tmpl = self.env['rsbu.operation.template'].create({
            'code': 'SHIP_UPD_A', 'name': 'Отгрузка',
            'resolver_key': 'shipment_upd', 'usn_recognition': 'income',
            'role_ids': [
                (0, 0, {'role': 'receivable',
                        'account_id': self._acc('62.01').id}),
                (0, 0, {'role': 'revenue',
                        'account_id': self._acc('90.01').id}),
                (0, 0, {'role': 'revenue_vat',
                        'account_id': self._acc('90.03').id}),
                (0, 0, {'role': 'vat_output',
                        'account_id': self._acc('68.НДС').id}),
                (0, 0, {'role': 'advance_received',
                        'account_id': self._acc('62.АВ').id}),
            ]})
        self.env['rsbu.operation.matrix'].create({
            'name': 'Исходящий инвойс → отгрузка (acceptance)',
            'doc_kind': 'out_invoice', 'template_id': tmpl.id})
        return tmpl

    def _advance_matrix(self):
        tmpl = self.env['rsbu.operation.template'].create({
            'code': 'ADV_A', 'name': 'Аванс',
            'resolver_key': 'customer_payment', 'usn_recognition': 'income',
            'role_ids': [
                (0, 0, {'role': 'bank', 'account_id': self._acc('51').id}),
                (0, 0, {'role': 'receivable',
                        'account_id': self._acc('62.01').id}),
                (0, 0, {'role': 'advance_received',
                        'account_id': self._acc('62.АВ').id}),
                (0, 0, {'role': 'vat_advance',
                        'account_id': self._acc('76.АВ').id}),
                (0, 0, {'role': 'vat_output',
                        'account_id': self._acc('68.НДС').id}),
            ]})
        self.env['rsbu.operation.matrix'].create({
            'name': 'Входящий → аванс (acceptance)',
            'doc_kind': 'payment_inbound', 'template_id': tmpl.id})
        return tmpl

    def _post_invoice(self, price=100000.0, qty=1, tax=None):
        line = {'name': 'Услуга А', 'product_id': self.product.id,
                'quantity': qty, 'price_unit': price}
        line['tax_ids'] = [(6, 0, tax.ids)] if tax else [(5, 0, 0)]
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.buyer.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, line)]})
        move.action_post()
        return move

    # -- 1. Реализация с НДС порождает отгрузочный СФ -------------------
    def test_realization_with_vat_creates_sf(self):
        """Инвойс с НДС 5% → реализация + отгрузочный СФ; vat_rate = факт."""
        self._shipment_matrix()
        move = self._post_invoice(price=100000.0, tax=self._tax(5.0))
        move.action_create_realization()
        real = move.rsbu_realization_id
        self.assertTrue(real)
        self.assertEqual(real.state, 'confirmed')
        sf = real.invoice_id
        self.assertTrue(sf, 'При наличии НДС должен появиться отгрузочный СФ')
        self.assertEqual(sf.invoice_type, 'shipment')
        # Ставка СФ — по фактическому налогу строки (5%), не форсированная.
        self.assertEqual(sf.vat_rate, 'vat_5')
        self.assertEqual(real.upd_function, '1')

    # -- 2. Реализация без НДС: СФ нет, УПД Функция=ДОП ------------------
    def test_realization_without_vat_no_sf(self):
        """Инвойс без НДС → только реализация; XML Функция=ДОП, валиден."""
        self._shipment_matrix()
        move = self._post_invoice(price=100000.0, tax=None)
        move.action_create_realization()
        real = move.rsbu_realization_id
        self.assertTrue(real)
        self.assertFalse(real.invoice_id, 'Без НДС отгрузочный СФ не создаётся')
        self.assertEqual(real.upd_function, '2')
        xml_bytes = real._upd_build_xml(filename='T')
        ok, errors = real._upd_validate_xml(xml_bytes)
        self.assertTrue(ok, 'ДОП-УПД не прошёл XSD: %s'
                        % '; '.join(errors[:5]))
        xml = xml_bytes.decode('cp1251')
        self.assertIn('Функция="ДОП"', xml)
        self.assertIn('<БезНДС>без НДС</БезНДС>', xml)

    # -- 3. XSD валиден для обоих случаев («1» и «2») -------------------
    def test_upd_xml_valid_both_cases(self):
        """УПД валиден по XSD и для СЧФДОП (с НДС), и для ДОП (без НДС)."""
        self._shipment_matrix()
        move_vat = self._post_invoice(price=100000.0, tax=self._tax(5.0))
        move_vat.action_create_realization()
        real_vat = move_vat.rsbu_realization_id
        xml_vat = real_vat._upd_build_xml(filename='T')
        ok_vat, err_vat = real_vat._upd_validate_xml(xml_vat)
        self.assertTrue(ok_vat, 'СЧФДОП не прошёл XSD: %s'
                        % '; '.join(err_vat[:5]))
        self.assertIn('Функция="СЧФДОП"', xml_vat.decode('cp1251'))

        move_nov = self._post_invoice(price=80000.0, tax=None)
        move_nov.action_create_realization()
        real_nov = move_nov.rsbu_realization_id
        xml_nov = real_nov._upd_build_xml(filename='T')
        ok_nov, err_nov = real_nov._upd_validate_xml(xml_nov)
        self.assertTrue(ok_nov, 'ДОП не прошёл XSD: %s'
                        % '; '.join(err_nov[:5]))
        self.assertIn('Функция="ДОП"', xml_nov.decode('cp1251'))

    # -- 4. Авансовый СФ рождается из платежа, без реализации -----------
    def test_advance_sf_still_from_payment(self):
        """Авансовый СФ создаётся из платежа, realization_id пуст."""
        self._advance_matrix()
        # Облагаемая сделка того же контрагента — условие авто-создания
        # авансового СФ (_rsbu_payment_is_taxable).
        self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.buyer.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Услуга А', 'product_id': self.product.id,
                'quantity': 1, 'price_unit': 100000.0,
                'tax_ids': [(6, 0, self._tax(5.0).ids)]})]})
        pay = self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer',
            'partner_id': self.buyer.id, 'amount': 105000.0,
            'rsbu_vat_amount': 5000.0,
            'journal_id': self.journal_bank.id})
        pay.action_post()
        advance = self.env['rsbu.invoice'].search([
            ('partner_id', '=', self.buyer.id),
            ('invoice_type', '=', 'advance'),
            ('company_id', '=', self.company.id)], limit=1)
        self.assertTrue(advance, 'Авансовый СФ должен создаться из платежа')
        self.assertEqual(advance.state, 'confirmed')
        self.assertFalse(advance.realization_id,
                         'У авансового СФ нет документа реализации')

    # -- 5. Книга продаж не зависит от наличия отгрузочного СФ ----------
    def test_sales_book_independent_of_sf(self):
        """Создание/удаление отгрузочного СФ не меняет число строк книги.

        Книга продаж строится на РСБУ-проводках реализации (резолвер), а не
        на rsbu.invoice. Поэтому её наполнение не зависит от того, выписан ли
        отгрузочный СФ.
        """
        self._shipment_matrix()
        move = self._post_invoice(price=100000.0, tax=self._tax(5.0))
        rsbu_move = move.rsbu_move_id
        self.assertTrue(rsbu_move, 'Проводка реализации должна сформироваться')
        BookLine = self.env['rsbu.vat.book.line']
        BookLine.recompute_period(rsbu_move.date, rsbu_move.date, self.company)
        before = BookLine.search_count([
            ('company_id', '=', self.company.id), ('book', '=', 'sales')])

        move.action_create_realization()
        real = move.rsbu_realization_id
        sf = real.invoice_id
        self.assertTrue(sf)
        BookLine.recompute_period(rsbu_move.date, rsbu_move.date, self.company)
        after_create = BookLine.search_count([
            ('company_id', '=', self.company.id), ('book', '=', 'sales')])
        self.assertEqual(after_create, before,
                         'Книга продаж не должна зависеть от создания СФ')

        sf.unlink()
        real.unlink()
        BookLine.recompute_period(rsbu_move.date, rsbu_move.date, self.company)
        after_delete = BookLine.search_count([
            ('company_id', '=', self.company.id), ('book', '=', 'sales')])
        self.assertEqual(after_delete, before,
                         'Книга продаж не должна зависеть от удаления СФ')

    # -- 6. Отображение ставки vat_rate по фактическим налогам ----------
    def test_vat_rate_mapping(self):
        """_upd_vat_rate: 20/10/7/5/0 → корректный vat_rate; mixed → max."""
        Realization = self.env['rsbu.realization']
        cases = [
            (20.0, 'vat_20'),
            (10.0, 'vat_10'),
            (7.0, 'vat_7'),
            (5.0, 'vat_5'),
            (0.0, 'vat_exempt'),
        ]
        for pct, expected in cases:
            move = self._post_invoice(price=10000.0, tax=self._tax(pct))
            self.assertEqual(Realization._upd_vat_rate(move), expected,
                             'Ставка %g%% → %s' % (pct, expected))

        # Строка без налогов → vat_exempt.
        move_none = self._post_invoice(price=10000.0, tax=None)
        self.assertEqual(Realization._upd_vat_rate(move_none), 'vat_exempt')

        # Смешанный инвойс (0% + 20%) → максимальная ненулевая = vat_20.
        move_mix = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.buyer.id,
            'company_id': self.company.id,
            'invoice_line_ids': [
                (0, 0, {'name': 'A', 'product_id': self.product.id,
                        'quantity': 1, 'price_unit': 1000.0,
                        'tax_ids': [(6, 0, self._tax(0.0).ids)]}),
                (0, 0, {'name': 'B', 'product_id': self.product.id,
                        'quantity': 1, 'price_unit': 1000.0,
                        'tax_ids': [(6, 0, self._tax(20.0).ids)]}),
            ]})
        self.assertEqual(Realization._upd_vat_rate(move_mix), 'vat_20',
                         'Смешанные ставки → максимальная ненулевая')

        # _has_vat: с ненулевым налогом True, без налога False.
        self.assertTrue(Realization._has_vat(move_mix))
        self.assertFalse(Realization._has_vat(move_none))
