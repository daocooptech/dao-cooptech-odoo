from freezegun import freeze_time

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRsbuVat(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.rsbu_enabled = True  # слой — по флажку организации (К4)
        cls.partner = cls.env['res.partner'].create({'name': 'Vat Клиент'})
        cls.journal_bank = cls.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', cls.company.id)],
            limit=1)
        cls.BookLine = cls.env['rsbu.vat.book.line']
        cls.Summary = cls.env['rsbu.vat.summary']

    def _acc(self, code):
        return self.env['rsbu.account'].search([
            ('code', '=', code),
            ('company_id', '=', self.env.company.id)], limit=1)

    def _advance_template(self):
        return self.env['rsbu.operation.template'].create({
            'code': 'ADV_V',
            'name': 'Аванс',
            'resolver_key': 'advance_received',
            'usn_recognition': 'income',
            'role_ids': [
                (0, 0, {'role': 'bank', 'account_id': self._acc('51').id}),
                (0, 0, {'role': 'advance_received',
                        'account_id': self._acc('62.АВ').id}),
                (0, 0, {'role': 'vat_advance',
                        'account_id': self._acc('76.АВ').id}),
                (0, 0, {'role': 'vat_output',
                        'account_id': self._acc('68.НДС').id}),
            ],
        })

    def _matrix(self, template):
        return self.env['rsbu.operation.matrix'].create({
            'name': 'Входящий → аванс',
            'doc_kind': 'payment_inbound',
            'template_id': template.id,
        })

    def _post_advance(self, amount=1050.0, vat=50.0):
        pay = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner.id,
            'amount': amount,
            'rsbu_vat_amount': vat,
            'journal_id': self.journal_bank.id,
        })
        pay.action_post()
        return pay

    def test_invoice_creation_and_sequence(self):
        inv = self.env['rsbu.invoice'].create({
            'invoice_type': 'advance',
            'partner_id': self.partner.id,
            'base_amount': 1000.0,
            'vat_amount': 50.0,
        })
        self.assertNotEqual(inv.name, '/')
        self.assertEqual(inv.invoice_type, 'advance')

    def test_sales_book_from_advance_vat(self):
        tmpl = self._advance_template()
        self._matrix(tmpl)
        pay = self._post_advance(amount=1050.0, vat=50.0)
        move = pay.rsbu_move_id
        self.BookLine.recompute_period(move.date, move.date, self.company)
        sales = self.BookLine.search([
            ('company_id', '=', self.company.id),
            ('book', '=', 'sales')])
        self.assertTrue(sales)
        # Авансовый НДС начислен по Кт 68.НДС = 50.
        self.assertEqual(sum(sales.mapped('vat_amount')), 50.0)

    def test_summary_payable(self):
        tmpl = self._advance_template()
        self._matrix(tmpl)
        pay = self._post_advance(amount=1050.0, vat=50.0)
        move = pay.rsbu_move_id
        self.BookLine.recompute_period(move.date, move.date, self.company)
        self.Summary.recompute_period(move.date, move.date, self.company)
        summary = self.Summary.search([
            ('company_id', '=', self.company.id)], limit=1)
        self.assertTrue(summary)
        # Начислено 50, вычетов нет -> к уплате 50.
        self.assertEqual(summary.vat_charged, 50.0)
        self.assertEqual(summary.vat_payable, 50.0)

    def test_recompute_idempotent(self):
        tmpl = self._advance_template()
        self._matrix(tmpl)
        pay = self._post_advance()
        move = pay.rsbu_move_id
        self.BookLine.recompute_period(move.date, move.date, self.company)
        first = self.BookLine.search_count(
            [('company_id', '=', self.company.id)])
        self.BookLine.recompute_period(move.date, move.date, self.company)
        second = self.BookLine.search_count(
            [('company_id', '=', self.company.id)])
        self.assertEqual(first, second)

    # ------------------------------------------------------------------
    # Расчёт налога УСН (rsbu.period.close.compute_usn_tax)
    # ------------------------------------------------------------------
    def test_usn_tax_computation(self):
        """Налог УСН = база(доход КУДиР) × ставка, база с исключённым НДС."""
        self.company.rsbu_usn_mode = 'usn_income'
        self.company.rsbu_usn_rate = 6.0
        tmpl = self._advance_template()
        self._matrix(tmpl)
        # Аванс 1050 c НДС 50 → доход КУДиР 1000 (НДС исключён).
        pay = self._post_advance(amount=1050.0, vat=50.0)
        # Закрытие за декабрь года платежа (охватывает весь год нараст. итогом).
        year = pay.rsbu_move_id.date.year
        pc = self.env['rsbu.period.close'].create({
            'period_month': '%s-12-01' % year,
            'company_id': self.company.id})
        pc.compute_usn_tax()
        # База = 1000 (доход без НДС), налог = 1000 × 6% = 60 (взносов нет).
        self.assertEqual(pc.usn_tax_base, 1000.0)
        self.assertEqual(pc.usn_tax_amount, 60.0)

    def test_advance_invoice_autocreated(self):
        """При поступлении аванса облагаемой сделки авансовый СФ создаётся
        автоматически (Дт 76.АВ — Кт 68.02)."""
        self.company.rsbu_vat_mode = 'vat_5'
        # Облагаемая реализация того же партнёра (инвойс источник правды).
        self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Услуги', 'quantity': 1, 'price_unit': 1000.0,
                'tax_ids': [(6, 0, self._vat5_tax().ids)]})],
        })
        tmpl = self._advance_template()
        self._matrix(tmpl)
        pay = self._post_advance(amount=1050.0, vat=0.0)
        invoices = self.env['rsbu.invoice'].search([
            ('partner_id', '=', self.partner.id),
            ('invoice_type', '=', 'advance'),
            ('company_id', '=', self.company.id)])
        self.assertTrue(invoices, 'Авансовый СФ должен создаться автоматически')
        self.assertEqual(invoices[0].state, 'confirmed')

    def _vat5_tax(self):
        tax = self.env['account.tax'].search([
            ('amount', '=', 5.0), ('type_tax_use', '=', 'sale'),
            ('company_id', '=', self.company.id)], limit=1)
        if not tax:
            tax = self.env['account.tax'].create({
                'name': 'НДС 5%', 'amount': 5.0, 'type_tax_use': 'sale',
                'company_id': self.company.id})
        return tax


@tagged('post_install', '-at_install')
@freeze_time('2027-01-15')
class TestPeriodClosePl(TransactionCase):
    """Закрытие месяца: 26→90.08, 90→99, 91→99, реформация 99→84 (декабрь).

    Дата заморожена на 2027-01-15: все месяцы 2026 завершены, поэтому
    проверка «месяц завершён» в _check_can_close не мешает тестам.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.rsbu_enabled = True  # слой — по флажку организации (К4)
        # Изолируем тесты финрезультата от налога УСН (ставка 0 → УСН=0,
        # проводок начисления на 99 не будет).
        cls.company.rsbu_usn_rate = 0.0
        cls.Account = cls.env['rsbu.account']
        cls.Move = cls.env['rsbu.move']
        # Догрузить типовой план (post_init_hook отрабатывает только при
        # установке; в тестовой БД гарантируем наличие 90.08/90.09/91.09/84).
        cls.env['rsbu.account.load.wizard'].create({
            'company_id': cls.company.id}).action_load()

    def _acc(self, code):
        return self.Account.search([
            ('code', '=', code),
            ('company_id', '=', self.company.id)], limit=1)

    def _post(self, date, lines):
        """Создать и провести rsbu.move из списка (code, debit, credit)."""
        move = self.Move.create({
            'date': date, 'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'account_id': self._acc(code).id,
                'debit': d, 'credit': c,
                'name': code}) for code, d, c in lines],
        })
        move.action_post()
        return move

    def _close(self, month_date):
        pc = self.env['rsbu.period.close'].create({
            'period_month': month_date, 'company_id': self.company.id})
        pc.action_close()
        return pc

    def _turnover(self, code, date_from, date_to):
        return self._acc(code).get_turnover(
            date_from=date_from, date_to=date_to,
            company_id=self.company.id, include_children=False)

    def test_close_expenses_26_to_9008(self):
        """Директ-костинг: 26 закрывается на 90.08, обнуляется."""
        # Расходы месяца: Дт 26 — Кт 51 (60 000). Контрсчёт 51 — без субконто.
        self._post('2026-02-15', [('26', 60000.0, 0.0), ('51', 0.0, 60000.0)])
        self._close('2026-02-01')
        # Оборот 26 за месяц: дебет 60 000 (расход) и кредит 60 000 (закрытие).
        t26 = self._turnover('26', '2026-02-01', '2026-02-28')
        self.assertEqual(round(t26['debit'] - t26['credit'], 2), 0.0,
                         'Счёт 26 должен обнулиться закрытием')
        # 90.08 получил расходы по дебету.
        t9008 = self._turnover('90.08', '2026-02-01', '2026-02-28')
        self.assertEqual(t9008['debit'], 60000.0)

    def test_close_90_profit_to_99(self):
        """Прибыль от продаж переносится на 99 (Дт 90.09 — Кт 99.01.1)."""
        profit_code = '99.01.1' if self._acc('99.01.1') else '99'
        # Выручка 100 000 (Кт 90.01), НДС 5000 (Дт 90.03), расходы 40 000 (26).
        # Контрсчёт 51 — без обязательных субконто.
        self._post('2026-03-31', [
            ('90.01', 0.0, 100000.0), ('51', 100000.0, 0.0)])
        self._post('2026-03-31', [
            ('90.03', 5000.0, 0.0), ('68.НДС', 0.0, 5000.0)])
        self._post('2026-03-15', [('26', 40000.0, 0.0), ('51', 0.0, 40000.0)])
        self._close('2026-03-01')
        # Финрезультат = 100000 − 5000 − 40000 = 55000 прибыль на 99 (кредит).
        bal99 = self._acc(profit_code).get_balance(
            date_to='2026-03-31', company_id=self.company.id,
            include_children=True)
        self.assertEqual(bal99['side'], 'credit')
        self.assertEqual(round(bal99['balance'], 2), 55000.0)
        # Субсчёт 90.09 обнулён (весь финрезультат ушёл на 99).
        b9009 = self._acc('90.09').get_balance(
            date_to='2026-03-31', company_id=self.company.id,
            include_children=False)
        self.assertEqual(round(b9009['balance'], 2), 0.0)

    def test_reform_balance_december(self):
        """Реформация декабря: сальдо 99 переносится на 84."""
        profit_code = '99.01.1' if self._acc('99.01.1') else '99'
        # Прибыль декабря: выручка 80 000, расходов нет.
        self._post('2026-12-31', [
            ('90.01', 0.0, 80000.0), ('51', 80000.0, 0.0)])
        self._close('2026-12-01')
        # После реформации 99 обнулён, 84 — кредитовое сальдо 80 000 (прибыль).
        bal99 = self._acc('99').get_balance(
            date_to='2026-12-31', company_id=self.company.id,
            include_children=True)
        self.assertEqual(round(bal99['balance'], 2), 0.0,
                         'Счёт 99 должен обнулиться реформацией')
        bal84 = self._acc('84').get_balance(
            date_to='2026-12-31', company_id=self.company.id)
        self.assertEqual(bal84['side'], 'credit')
        self.assertEqual(round(bal84['balance'], 2), 80000.0)

    def test_reopen_reverts_closing(self):
        """Переоткрытие удаляет все регламентные проводки закрытия."""
        self._post('2026-04-15', [('26', 30000.0, 0.0), ('51', 0.0, 30000.0)])
        pc = self._close('2026-04-01')
        self.assertTrue(pc.move_ids)
        self.assertEqual(pc.state, 'done')
        pc.action_reopen()
        self.assertFalse(pc.move_ids)
        self.assertEqual(pc.state, 'draft')
        # 26 снова с дебетовым оборотом (закрытие откатилось).
        t26 = self._turnover('26', '2026-04-01', '2026-04-30')
        self.assertEqual(round(t26['debit'] - t26['credit'], 2), 30000.0)

    def test_accounting_start_allows_first_month(self):
        """Месяц начала учёта закрывается свободно (предыдущий не нужен)."""
        # Есть проводки и в мае, и в июне, но учёт ведётся с июня.
        self.company.rsbu_accounting_start = '2026-06-01'
        self._post('2026-05-20', [('26', 10000.0, 0.0), ('51', 0.0, 10000.0)])
        self._post('2026-06-20', [('26', 20000.0, 0.0), ('51', 0.0, 20000.0)])
        # Июнь (месяц начала учёта) закрывается без требования закрыть май.
        pc = self._close('2026-06-01')
        self.assertEqual(pc.state, 'done')

    def test_accounting_start_blocks_earlier_month(self):
        """Нельзя закрыть месяц раньше даты начала учёта."""
        from odoo.exceptions import UserError
        self.company.rsbu_accounting_start = '2026-06-01'
        self._post('2026-05-20', [('26', 10000.0, 0.0), ('51', 0.0, 10000.0)])
        pc = self.env['rsbu.period.close'].create({
            'period_month': '2026-05-01', 'company_id': self.company.id})
        with self.assertRaises(UserError):
            pc.action_close()

    def test_cannot_close_future_month(self):
        """Нельзя закрыть незавершённый/будущий месяц (заморожен 2027-01-15)."""
        from odoo.exceptions import UserError
        pc = self.env['rsbu.period.close'].create({
            'period_month': '2027-02-01', 'company_id': self.company.id})
        with self.assertRaises(UserError):
            pc.action_close()

    def test_close_requires_previous_month(self):
        """Нельзя закрыть месяц, если предыдущий (с проводками) не закрыт."""
        from odoo.exceptions import UserError
        # Проводки в марте и апреле.
        self._post('2026-03-15', [('26', 10000.0, 0.0), ('51', 0.0, 10000.0)])
        self._post('2026-04-15', [('26', 20000.0, 0.0), ('51', 0.0, 20000.0)])
        # Апрель без закрытого марта — блокируется.
        pc_apr = self.env['rsbu.period.close'].create({
            'period_month': '2026-04-01', 'company_id': self.company.id})
        with self.assertRaises(UserError):
            pc_apr.action_close()
        # Закрываем март, затем апрель проходит.
        self._close('2026-03-01')
        pc_apr.action_close()
        self.assertEqual(pc_apr.state, 'done')


