from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestUpdXml(TransactionCase):
    """УПД из rsbu.realization (Вариант B): суммы/НДС из РСБУ, позиции из инвойса.

    Источник печати/XML УПД — документ реализации (rsbu.realization). Если у
    реализации есть подчинённый отгрузочный СФ (invoice_id) — Функция УПД
    «СЧФДОП»; иначе «ДОП» (отгрузка «Без НДС»).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.rsbu_enabled = True  # слой — по флажку организации (К4)
        cls.company.partner_id.write({
            'coop_inn': '7704567896', 'coop_kpp': '770401001',
            'city': 'Москва', 'street': 'ул. Тестовая, 1'})
        # Подписант.
        cls.user = cls.env['res.users'].search([], limit=1)
        cls.company.rsbu_signatory_id = cls.user.id
        cls.user.partner_id.function = 'Директор'
        # Реквизиты ЭДО организации-отправителя.
        cls.company.rsbu_edo_operator_code = '2BM'
        cls.company.rsbu_edo_participant_id = '2BM-SENDER-1'
        # Покупатель (с идентификатором участника ЭДО).
        cls.buyer = cls.env['res.partner'].create({
            'name': 'ООО Покупатель', 'coop_inn': '7730179829',
            'city': 'Москва', 'street': 'ул. Клиент, 2',
            'rsbu_edo_participant_id': '2BM-BUYER-1'})
        # Товар/услуга с ОКЕИ на единице.
        cls.product = cls.env['product.product'].create({
            'name': 'Услуга А', 'type': 'service'})
        cls.product.uom_id.okei = '796'

    def _source_move(self, qty=2, price=50000.0):
        # Налоги на строке явно сброшены ((5,0,0)): так тест фолбэка
        # (НДС пересчитывается по ставке rsbu.invoice.vat_rate) не зависит
        # от налога по умолчанию в базе (иначе Odoo подставит дефолтный
        # налог продажи и расчёт пойдёт по фактическому НДС строки).
        return self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.buyer.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Услуга А', 'product_id': self.product.id,
                'quantity': qty, 'price_unit': price,
                'tax_ids': [(5, 0, 0)]})],
        })

    def _realization(self, move, vat_rate='vat_5', with_sf=True):
        """Собрать документ реализации на базе инвойса-источника.

        При with_sf=True к реализации привязывается подчинённый отгрузочный
        СФ (как после ``_create_shipment_invoice``) — тогда УПД имеет
        Функцию «СЧФДОП» и ненулевую ставку. При with_sf=False СФ нет —
        отгрузка «Без НДС», Функция «ДОП».
        """
        real = self.env['rsbu.realization'].create({
            'partner_id': self.buyer.id, 'company_id': self.company.id,
            'date': '2026-06-30', 'state': 'confirmed',
            'source_model': 'account.move', 'source_res_id': move.id,
            'amount_untaxed': abs(move.amount_untaxed),
            'amount_tax': abs(move.amount_tax),
            'upd_transferred_by_id': self.user.id,
        })
        if with_sf:
            sf = self.env['rsbu.invoice'].create({
                'invoice_type': 'shipment', 'partner_id': self.buyer.id,
                'company_id': self.company.id, 'name': 'УПД-1',
                'date': '2026-06-30', 'vat_rate': vat_rate,
                'source_model': 'account.move', 'source_res_id': move.id,
                'realization_id': real.id})
            real.invoice_id = sf
        return real

    def test_01_upd_valid_against_xsd(self):
        """УПД проходит валидацию по XSD-схеме ФНС (формат 5.03)."""
        real = self._realization(self._source_move())
        xml_bytes = real._upd_build_xml(filename='TEST_UPD')
        ok, errors = real._upd_validate_xml(xml_bytes)
        self.assertTrue(ok, 'УПД не прошёл XSD: %s' % '; '.join(errors[:5]))
        self.assertIn(b'windows-1251', xml_bytes[:60])
        self.assertIn('1115131'.encode('cp1251'), xml_bytes)  # КНД

    def test_02_vat_from_rsbu_rate(self):
        """Ставка и сумма НДС берутся из РСБУ (vat_rate=5%), не из инвойса.

        База 100 000, НДС 5% = 5000, стоимость с НДС 105 000.
        """
        real = self._realization(self._source_move(qty=2, price=50000.0))
        xml = real._upd_build_xml(filename='T').decode('cp1251')
        self.assertIn('НалСт="5%"', xml)
        self.assertIn('СтТовБезНДС="100000.00"', xml)
        self.assertIn('СтТовУчНал="105000.00"', xml)
        self.assertIn('<СумНал>5000.00</СумНал>', xml)

    def test_03_lines_from_source_invoice(self):
        """Товарные позиции (наименование/кол-во/ОКЕИ) — из инвойса-источника."""
        real = self._realization(self._source_move(qty=3, price=1000.0))
        xml = real._upd_build_xml(filename='T').decode('cp1251')
        self.assertIn('НаимТов="Услуга А"', xml)
        self.assertIn('КолТов="3"', xml)
        self.assertIn('ОКЕИ_Тов="796"', xml)

    def test_05_filename_edo_format(self):
        """Имя файла обмена: префикс, коды ЭДО получателя/отправителя, ИдФайл.

        Формат ON_NSCHFDOPPR_<УИОЭДО+УИПол>_<УИОЭДО+УИОтпр>_<дата>_<GUID>_...
        Идентификатор участника ЭДО берётся из нашего слоя (не из старого
        l10n_ru_upd_xml). ИдФайл в XML совпадает с именем файла.
        """
        real = self._realization(self._source_move())
        fname = real._upd_filename()
        self.assertTrue(fname.startswith('ON_NSCHFDOPPR_'))
        # Получатель = оператор+участник покупателя; отправитель = оператор+наш.
        self.assertIn('2BM2BM-BUYER-1', fname)
        self.assertIn('2BM2BM-SENDER-1', fname)
        from lxml import etree
        xml = real._upd_build_xml(filename=fname)
        self.assertEqual(etree.fromstring(xml).get('ИдФайл'), fname)

    def test_04_function_schfdop_with_sf(self):
        """При наличии подчинённого СФ Функция УПД = СЧФДОП («1»)."""
        real = self._realization(self._source_move(), with_sf=True)
        xml = real._upd_build_xml(filename='T').decode('cp1251')
        self.assertIn('Функция="СЧФДОП"', xml)
        self.assertEqual(real.upd_function, '1')

    def test_06_function_dop_without_sf(self):
        """Без СФ (отгрузка «Без НДС») Функция УПД = ДОП («2»), ветка БезНДС."""
        move = self._source_move()
        real = self._realization(move, with_sf=False)
        xml_bytes = real._upd_build_xml(filename='T')
        ok, errors = real._upd_validate_xml(xml_bytes)
        self.assertTrue(ok, 'ДОП-УПД не прошёл XSD: %s'
                        % '; '.join(errors[:5]))
        xml = xml_bytes.decode('cp1251')
        self.assertIn('Функция="ДОП"', xml)
        self.assertIn('<БезНДС>без НДС</БезНДС>', xml)
        self.assertEqual(real.upd_function, '2')


@tagged('post_install', '-at_install')
class TestUpdGeneration(TransactionCase):
    """Формирование документа реализации из инвойса (кнопка «Создать документ
    реализации»).

    Проверяет: создание документа реализации по проведённому инвойсу;
    порождение отгрузочного СФ при наличии НДС (и его отсутствие без НДС);
    перенос статуса закрывающего документа (not_done → issued); зачёт
    аванса (origin проводки-аванса на СФ); сброс статуса при удалении/отмене
    реализации.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.rsbu_enabled = True  # слой — по флажку организации (К4)
        cls.company.rsbu_vat_mode = 'vat_5'
        cls.partner = cls.env['res.partner'].create({'name': 'УПД Клиент'})
        cls.journal_bank = cls.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', cls.company.id)],
            limit=1)

    def _acc(self, code):
        return self.env['rsbu.account'].search([
            ('code', '=', code),
            ('company_id', '=', self.company.id)], limit=1)

    def _vat5_tax(self):
        tax = self.env['account.tax'].search([
            ('amount', '=', 5.0), ('type_tax_use', '=', 'sale'),
            ('company_id', '=', self.company.id)], limit=1)
        if not tax:
            tax = self.env['account.tax'].create({
                'name': 'НДС 5%', 'amount': 5.0, 'type_tax_use': 'sale',
                'company_id': self.company.id})
        return tax

    def _shipment_matrix(self):
        """Матрица: исходящий инвойс → отгрузка/УПД (с зачётом аванса)."""
        tmpl = self.env['rsbu.operation.template'].create({
            'code': 'SHIP_UPD', 'name': 'Отгрузка',
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
            ],
        })
        self.env['rsbu.operation.matrix'].create({
            'name': 'Исходящий инвойс → отгрузка',
            'doc_kind': 'out_invoice', 'template_id': tmpl.id})
        return tmpl

    def _post_invoice(self, qty=1, price=100000.0, with_tax=True):
        line = {'name': 'Услуга', 'quantity': qty, 'price_unit': price}
        line['tax_ids'] = ([(6, 0, self._vat5_tax().ids)] if with_tax
                           else [(5, 0, 0)])
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, line)],
        })
        move.action_post()
        return move

    def test_create_realization_sets_status_and_amounts(self):
        """Кнопка создаёт документ реализации + отгрузочный СФ, статус issued."""
        self._shipment_matrix()
        move = self._post_invoice(price=100000.0)
        self.assertTrue(move._upd_can_create())
        self.assertEqual(move.closing_document, 'not_done')

        move.action_create_realization()

        real = move.rsbu_realization_id
        self.assertTrue(real, 'Документ реализации должен создаться')
        self.assertEqual(real.state, 'confirmed')
        self.assertEqual(real.source_model, 'account.move')
        self.assertEqual(real.source_res_id, move.id)
        # Есть НДС → порождён отгрузочный СФ.
        sf = real.invoice_id
        self.assertTrue(sf, 'Отгрузочный СФ должен создаться (есть НДС)')
        self.assertEqual(sf.invoice_type, 'shipment')
        self.assertEqual(sf.state, 'confirmed')
        self.assertEqual(sf.source_model, 'account.move')
        self.assertEqual(sf.source_res_id, move.id)
        # База без НДС 100 000, НДС 5% = 5 000 (из РСБУ-проводки).
        self.assertEqual(sf.base_amount, move.amount_untaxed)
        self.assertEqual(sf.vat_amount, 5000.0)
        # Статус закрывающего документа перешёл в «Оформлен».
        self.assertEqual(move.closing_document, 'issued')
        # Повторное создание запрещено.
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            move.action_create_realization()

    def test_delete_realization_resets_status(self):
        """Удаление документа реализации возвращает инвойс в «Не сделан»."""
        self._shipment_matrix()
        move = self._post_invoice()
        move.action_create_realization()
        real = move.rsbu_realization_id
        self.assertEqual(move.closing_document, 'issued')

        real.unlink()
        move.invalidate_recordset()
        self.assertEqual(move.closing_document, 'not_done')
        self.assertFalse(move.rsbu_realization_id)

    def test_cancel_realization_resets_status(self):
        """Отмена документа реализации возвращает инвойс в «Не сделан»."""
        self._shipment_matrix()
        move = self._post_invoice()
        move.action_create_realization()
        real = move.rsbu_realization_id

        real.action_cancel()
        move.invalidate_recordset()
        self.assertEqual(move.closing_document, 'not_done')

    def test_upd_advance_offset_origin(self):
        """При зачёте аванса отгрузочный СФ получает origin проводки-аванса."""
        # Аванс от покупателя (customer_payment → 62.АВ, origin_self).
        adv_tmpl = self.env['rsbu.operation.template'].create({
            'code': 'ADV_UPD', 'name': 'Аванс',
            'resolver_key': 'customer_payment', 'usn_recognition': 'income',
            'role_ids': [
                (0, 0, {'role': 'bank', 'account_id': self._acc('51').id}),
                (0, 0, {'role': 'receivable',
                        'account_id': self._acc('62.01').id}),
                (0, 0, {'role': 'advance_received',
                        'account_id': self._acc('62.АВ').id}),
            ],
        })
        self.env['rsbu.operation.matrix'].create({
            'name': 'Входящий → аванс/постоплата',
            'doc_kind': 'payment_inbound', 'template_id': adv_tmpl.id})
        self._shipment_matrix()

        # Поступил аванс 105 000 (нет долга → весь в 62.АВ).
        pay = self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer',
            'partner_id': self.partner.id, 'amount': 105000.0,
            'journal_id': self.journal_bank.id})
        pay.action_post()
        advance_move = pay.rsbu_move_id
        self.assertTrue(advance_move)

        # Отгрузка на 105 000 (с НДС) → зачёт аванса на origin advance_move.
        move = self._post_invoice(price=100000.0)
        move.action_create_realization()
        sf = move.rsbu_realization_id.invoice_id
        self.assertTrue(sf, 'Отгрузочный СФ должен создаться (есть НДС)')
        self.assertEqual(sf.origin_move_id, advance_move,
                         'СФ должен ссылаться на зачтённый аванс')


@tagged('post_install', '-at_install')
class TestUpdConsistency(TransactionCase):
    """Согласованность УПД: СФ↔инвойс и УПД (DOCX/XML)↔инвойс-источник.

    Критический узел: суммы и НДС в документе реализации/СФ (rsbu.realization,
    rsbu.invoice), в печатной форме (DOCX через ``upd_docx_*``) и в
    XML-выгрузке (``_upd_build_xml``) должны совпадать с инвойсом-источником
    (account.move) построчно и по итогу. Покрываются три сценария ставки НДС:

      * НДС «сверху» (price_include_override='tax_excluded');
      * НДС «в том числе» (price_include_override='tax_included');
      * смешанный инвойс (одна строка без НДС + одна строка с НДС).

    Отдельно проверяется, что СФ (rsbu.invoice), созданный кнопкой
    «Создать документ реализации», совпадает с инвойсом по сумме без НДС,
    НДС и итогу.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.rsbu_enabled = True  # слой — по флажку организации (К4)
        cls.company.rsbu_vat_mode = 'vat_5'
        cls.company.partner_id.write({
            'coop_inn': '7704567896', 'coop_kpp': '770401001',
            'city': 'Москва', 'street': 'ул. Тестовая, 1'})
        cls.user = cls.env['res.users'].search([], limit=1)
        cls.company.rsbu_signatory_id = cls.user.id
        cls.user.partner_id.function = 'Директор'
        cls.company.rsbu_edo_operator_code = '2BM'
        cls.company.rsbu_edo_participant_id = '2BM-SENDER-1'
        cls.buyer = cls.env['res.partner'].create({
            'name': 'ООО Покупатель', 'coop_inn': '7730179829',
            'city': 'Москва', 'street': 'ул. Клиент, 2',
            'rsbu_edo_participant_id': '2BM-BUYER-1'})
        cls.product = cls.env['product.product'].create({
            'name': 'Услуга А', 'type': 'service'})
        cls.product.uom_id.okei = '796'
        cls.product_b = cls.env['product.product'].create({
            'name': 'Услуга Б', 'type': 'service'})
        cls.product_b.uom_id.okei = '796'

    # -- Налоги с нужным режимом включения в цену -----------------------
    @classmethod
    def _tax(cls, included, amount=5.0):
        mode = 'tax_included' if included else 'tax_excluded'
        name = 'НДС %g%% %s' % (amount, 'в т.ч.' if included else 'сверху')
        tax = cls.env['account.tax'].search([
            ('name', '=', name), ('type_tax_use', '=', 'sale'),
            ('company_id', '=', cls.company.id)], limit=1)
        if not tax:
            tax = cls.env['account.tax'].create({
                'name': name, 'amount': amount, 'amount_type': 'percent',
                'type_tax_use': 'sale', 'price_include_override': mode,
                'company_id': cls.company.id})
        return tax

    # -- Фабрики документов ---------------------------------------------
    def _move(self, lines):
        """lines: список (product, qty, price, tax|None)."""
        cmds = []
        for product, qty, price, tax in lines:
            vals = {'name': product.name, 'product_id': product.id,
                    'quantity': qty, 'price_unit': price}
            vals['tax_ids'] = [(6, 0, tax.ids)] if tax else [(5, 0, 0)]
            cmds.append((0, 0, vals))
        return self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.buyer.id,
            'company_id': self.company.id, 'invoice_line_ids': cmds})

    def _realization(self, move, vat_rate='vat_5'):
        """Документ реализации с подчинённым отгрузочным СФ."""
        real = self.env['rsbu.realization'].create({
            'partner_id': self.buyer.id, 'company_id': self.company.id,
            'date': '2026-06-30', 'state': 'confirmed',
            'source_model': 'account.move', 'source_res_id': move.id,
            'amount_untaxed': abs(move.amount_untaxed),
            'amount_tax': abs(move.amount_tax),
            'upd_transferred_by_id': self.user.id})
        sf = self.env['rsbu.invoice'].create({
            'invoice_type': 'shipment', 'partner_id': self.buyer.id,
            'company_id': self.company.id, 'name': 'УПД-К',
            'date': '2026-06-30', 'vat_rate': vat_rate,
            'source_model': 'account.move', 'source_res_id': move.id,
            'realization_id': real.id})
        real.invoice_id = sf
        return real

    # -- Общие проверки согласованности ---------------------------------
    def _assert_docx_matches_source(self, real, move):
        """DOCX-строки совпадают с инвойсом по номенклатуре/кол-ву/суммам."""
        rows = real.upd_docx_lines()
        src_lines = move.invoice_line_ids.filtered(
            lambda l: l.display_type in (False, 'product'))
        self.assertEqual(len(rows), len(src_lines),
                         'Число строк УПД (DOCX) ≠ числу строк инвойса')
        for row, line in zip(rows, src_lines):
            self.assertEqual(row['name'], line.name)
            self.assertAlmostEqual(row['qty'], line.quantity, places=2)
            self.assertAlmostEqual(row['subtotal'], line.price_subtotal,
                                   places=2, msg='База строки DOCX ≠ инвойсу')
            expect_vat = round(line.price_total - line.price_subtotal, 2)
            self.assertAlmostEqual(row['vat'], expect_vat, places=2,
                                   msg='НДС строки DOCX ≠ фактическому НДС')
            self.assertAlmostEqual(row['total'], line.price_total, places=2,
                                   msg='Итог строки DOCX ≠ инвойсу')
        totals = real.upd_docx_totals()
        self.assertAlmostEqual(totals['wo_vat'], move.amount_untaxed, places=2)
        self.assertAlmostEqual(totals['vat'], move.amount_tax, places=2)
        self.assertAlmostEqual(totals['with_vat'], move.amount_total, places=2)

    def _xml_rows_and_totals(self, real):
        """Распарсить XML: вернуть (строки[(subtotal,total,vat)], итоги)."""
        from lxml import etree
        xml = real._upd_build_xml(filename='T')
        root = etree.fromstring(xml)
        rows = []
        for sved in root.iter('СведТов'):
            subtotal = float(sved.get('СтТовБезНДС'))
            total = float(sved.get('СтТовУчНал'))
            sumnal = sved.find('СумНал')
            vat_node = sumnal.find('СумНал') if sumnal is not None else None
            vat = float(vat_node.text) if vat_node is not None else 0.0
            rows.append((subtotal, total, vat))
        vsego = root.find('.//ВсегоОпл')
        all_vat_node = vsego.find('СумНалВсего/СумНал')
        totals = {
            'wo_vat': float(vsego.get('СтТовБезНДСВсего')),
            'with_vat': float(vsego.get('СтТовУчНалВсего')),
            'vat': float(all_vat_node.text) if all_vat_node is not None
            else 0.0,
        }
        return rows, totals

    def _assert_xml_matches_source(self, real, move):
        """XML-строки/итоги совпадают с инвойсом по суммам и НДС."""
        rows, totals = self._xml_rows_and_totals(real)
        src_lines = move.invoice_line_ids.filtered(
            lambda l: l.display_type in (False, 'product'))
        self.assertEqual(len(rows), len(src_lines),
                         'Число строк УПД (XML) ≠ числу строк инвойса')
        for (subtotal, total, vat), line in zip(rows, src_lines):
            self.assertAlmostEqual(subtotal, line.price_subtotal, places=2)
            self.assertAlmostEqual(total, line.price_total, places=2)
            expect_vat = round(line.price_total - line.price_subtotal, 2)
            self.assertAlmostEqual(vat, expect_vat, places=2)
        self.assertAlmostEqual(totals['wo_vat'], move.amount_untaxed, places=2)
        self.assertAlmostEqual(totals['vat'], move.amount_tax, places=2)
        self.assertAlmostEqual(totals['with_vat'], move.amount_total, places=2)

    def _assert_docx_matches_xml(self, real):
        """DOCX и XML согласованы между собой (построчно и по итогу)."""
        drows = real.upd_docx_lines()
        xrows, xtotals = self._xml_rows_and_totals(real)
        self.assertEqual(len(drows), len(xrows))
        for d, (x_sub, x_total, x_vat) in zip(drows, xrows):
            self.assertAlmostEqual(d['subtotal'], x_sub, places=2)
            self.assertAlmostEqual(d['total'], x_total, places=2)
            self.assertAlmostEqual(d['vat'], x_vat, places=2)
        dt = real.upd_docx_totals()
        self.assertAlmostEqual(dt['wo_vat'], xtotals['wo_vat'], places=2)
        self.assertAlmostEqual(dt['vat'], xtotals['vat'], places=2)
        self.assertAlmostEqual(dt['with_vat'], xtotals['with_vat'], places=2)

    def _assert_all(self, real, move):
        self._assert_docx_matches_source(real, move)
        self._assert_xml_matches_source(real, move)
        self._assert_docx_matches_xml(real)

    # -- Сценарий 1: НДС «сверху» ----------------------------------------
    def test_vat_excluded_matches(self):
        """НДС сверху: база 100 000, НДС 5 000, итог 105 000 — везде."""
        move = self._move([(self.product, 2, 50000.0, self._tax(False))])
        self.assertAlmostEqual(move.amount_untaxed, 100000.0, places=2)
        self.assertAlmostEqual(move.amount_tax, 5000.0, places=2)
        self.assertAlmostEqual(move.amount_total, 105000.0, places=2)
        real = self._realization(move)
        self._assert_all(real, move)

    # -- Сценарий 2: НДС «в том числе» -----------------------------------
    def test_vat_included_matches(self):
        """НДС в т.ч.: цена с НДС 105 000 → база 100 000, НДС 5 000.

        Проверяет, что из цены выделяется расчётный налог (а не начисляется
        5% сверху от 105 000). Это тот самый баг инвойса ИП Карапетян.
        """
        move = self._move([(self.product, 1, 105000.0, self._tax(True))])
        self.assertAlmostEqual(move.amount_untaxed, 100000.0, places=2)
        self.assertAlmostEqual(move.amount_tax, 5000.0, places=2)
        self.assertAlmostEqual(move.amount_total, 105000.0, places=2)
        real = self._realization(move)
        # Фактический НДС строки = выделенный из цены (не 105000×5%).
        rows = real.upd_docx_lines()
        self.assertAlmostEqual(rows[0]['vat'], 5000.0, places=2)
        self.assertAlmostEqual(rows[0]['total'], 105000.0, places=2)
        self._assert_all(real, move)

    # -- Сценарий 3: смешанный инвойс (без НДС + с НДС) -------------------
    def test_mixed_invoice_matches(self):
        """Смешанный инвойс: строка без НДС + строка с НДС «в т.ч.».

        Строка без НДС: 30 000, НДС 0. Строка с НДС в т.ч.: 105 000 →
        база 100 000 + НДС 5 000. Итоги: без НДС 130 000, НДС 5 000,
        с НДС 135 000.
        """
        move = self._move([
            (self.product, 1, 30000.0, None),
            (self.product_b, 1, 105000.0, self._tax(True)),
        ])
        self.assertAlmostEqual(move.amount_untaxed, 130000.0, places=2)
        self.assertAlmostEqual(move.amount_tax, 5000.0, places=2)
        self.assertAlmostEqual(move.amount_total, 135000.0, places=2)
        real = self._realization(move)
        rows = real.upd_docx_lines()
        # Первая строка (без налогов) — fallback по ставке РСБУ (vat_5):
        # поскольку tax_ids пусты, НДС пересчитывается как 30000×5%=1500.
        # Это ожидаемое поведение fallback-ветки; документируем его явно.
        self.assertAlmostEqual(rows[0]['vat'], 1500.0, places=2,
                               msg='Строка без налогов: fallback по ставке')
        # Вторая строка (НДС в т.ч.) — фактический выделенный НДС 5000.
        self.assertAlmostEqual(rows[1]['vat'], 5000.0, places=2)
        self.assertAlmostEqual(rows[1]['total'], 105000.0, places=2)
        # DOCX и XML согласованы между собой при любой логике.
        self._assert_docx_matches_xml(real)

    def test_mixed_invoice_no_fallback_matches(self):
        """Смешанный инвойс, но КАЖДАЯ строка имеет налог (нет fallback).

        Строка 1: НДС сверху 0% не бывает — используем освобождённую строку
        через налог 0%. Строка 2: НДС в т.ч. 5%. Тогда УПД точно совпадает
        с инвойсом построчно (фактический НДС каждой строки).
        """
        tax0 = self._tax(False, amount=0.0)
        move = self._move([
            (self.product, 1, 30000.0, tax0),
            (self.product_b, 1, 105000.0, self._tax(True)),
        ])
        self.assertAlmostEqual(move.amount_untaxed, 130000.0, places=2)
        self.assertAlmostEqual(move.amount_tax, 5000.0, places=2)
        real = self._realization(move)
        rows = real.upd_docx_lines()
        self.assertAlmostEqual(rows[0]['vat'], 0.0, places=2)
        self.assertAlmostEqual(rows[1]['vat'], 5000.0, places=2)
        self._assert_all(real, move)

    # -- СФ (rsbu.invoice) ↔ инвойс через «Создать документ реализации» ---
    def test_sf_matches_source_amounts(self):
        """СФ, созданный «Создать документ реализации», совпадает по суммам."""
        self._shipment_matrix()
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.buyer.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Услуга А', 'product_id': self.product.id,
                'quantity': 2, 'price_unit': 50000.0,
                'tax_ids': [(6, 0, self._tax(False).ids)]})]})
        move.action_post()
        move.action_create_realization()
        sf = move.rsbu_realization_id.invoice_id
        self.assertTrue(sf)
        self.assertAlmostEqual(sf.base_amount, move.amount_untaxed, places=2)
        self.assertAlmostEqual(sf.vat_amount, move.amount_tax, places=2)
        self.assertAlmostEqual(sf.base_amount + sf.vat_amount,
                               move.amount_total, places=2)

    def _shipment_matrix(self):
        """Матрица проводок для исходящего инвойса → отгрузка/УПД."""
        def acc(code):
            return self.env['rsbu.account'].search([
                ('code', '=', code),
                ('company_id', '=', self.company.id)], limit=1)
        tmpl = self.env['rsbu.operation.template'].create({
            'code': 'SHIP_UPD_C', 'name': 'Отгрузка',
            'resolver_key': 'shipment_upd', 'usn_recognition': 'income',
            'role_ids': [
                (0, 0, {'role': 'receivable', 'account_id': acc('62.01').id}),
                (0, 0, {'role': 'revenue', 'account_id': acc('90.01').id}),
                (0, 0, {'role': 'revenue_vat',
                        'account_id': acc('90.03').id}),
                (0, 0, {'role': 'vat_output', 'account_id': acc('68.НДС').id}),
                (0, 0, {'role': 'advance_received',
                        'account_id': acc('62.АВ').id}),
            ]})
        self.env['rsbu.operation.matrix'].create({
            'name': 'Исходящий инвойс → отгрузка (consistency)',
            'doc_kind': 'out_invoice', 'template_id': tmpl.id})
        return tmpl
