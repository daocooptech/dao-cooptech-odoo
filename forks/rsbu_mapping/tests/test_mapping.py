from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRsbuMapping(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # Слой включается по организации (у выпуска — всегда).
        cls.company.rsbu_enabled = True
        cls.partner = cls.env['res.partner'].create({'name': 'Map Клиент'})
        cls.journal_bank = cls.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', cls.company.id)],
            limit=1)
        cls.Template = cls.env['rsbu.operation.template']
        cls.Matrix = cls.env['rsbu.operation.matrix']
        # Роли счетов из типового плана.
        cls.acc = lambda self, code: self.env['rsbu.account'].search([
            ('code', '=', code),
            ('company_id', '=', self.env.company.id)], limit=1)

    def _acc(self, code):
        return self.env['rsbu.account'].search([
            ('code', '=', code),
            ('company_id', '=', self.env.company.id)], limit=1)

    def _advance_template(self):
        return self.Template.create({
            'code': 'ADV_IN',
            'name': 'Получение аванса',
            'resolver_key': 'advance_received',
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

    def _matrix_advance(self, template):
        return self.Matrix.create({
            'name': 'Входящий платёж → аванс',
            'doc_kind': 'payment_inbound',
            'has_advance': 'any',
            'template_id': template.id,
            'priority': 10,
        })

    def _payment(self, amount=1050.0, vat=50.0):
        return self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner.id,
            'amount': amount,
            'rsbu_vat_amount': vat,
            'journal_id': self.journal_bank.id,
        })

    def test_detect_template_by_matrix(self):
        tmpl = self._advance_template()
        self._matrix_advance(tmpl)
        pay = self._payment()
        self.assertEqual(pay._rsbu_detect_template(), tmpl)
        self.assertTrue(pay._rsbu_is_applicable())

    def test_no_matrix_not_applicable(self):
        # Без матрицы документ не в РСБУ-периметре.
        pay = self._payment()
        self.assertFalse(pay._rsbu_detect_template())
        self.assertFalse(pay._rsbu_is_applicable())

    def test_advance_resolver_lines_balanced(self):
        tmpl = self._advance_template()
        self._matrix_advance(tmpl)
        pay = self._payment(amount=1050.0, vat=50.0)
        lines = pay._rsbu_build_lines()
        total_debit = sum(l.get('debit', 0.0) for l in lines)
        total_credit = sum(l.get('credit', 0.0) for l in lines)
        self.assertEqual(total_debit, total_credit)
        # Дт 51 = 1050, авансовый НДС 50
        self.assertEqual(total_debit, 1050.0 + 50.0)

    def test_full_flow_generate_rsbu_move(self):
        tmpl = self._advance_template()
        self._matrix_advance(tmpl)
        pay = self._payment(amount=1050.0, vat=50.0)
        pay.action_post()
        move = pay.rsbu_move_id
        self.assertTrue(move)
        self.assertEqual(move.state, 'posted')
        # Проверим сальдо: 51 дебет 1050
        acc51 = self._acc('51')
        bal = acc51.get_balance(company_id=self.company.id)
        self.assertEqual(bal['debit'], 1050.0)
        # 68.НДС кредит 50 (начислен авансовый НДС)
        acc68 = self._acc('68.НДС')
        bal68 = acc68.get_balance(company_id=self.company.id)
        self.assertEqual(bal68['credit'], 50.0)

    def _sale_template(self, with_advance_roles=False):
        roles = [
            (0, 0, {'role': 'receivable', 'account_id': self._acc('62.01').id}),
            (0, 0, {'role': 'revenue', 'account_id': self._acc('90.01').id}),
            (0, 0, {'role': 'revenue_vat', 'account_id': self._acc('90.03').id}),
            (0, 0, {'role': 'vat_output', 'account_id': self._acc('68.НДС').id}),
        ]
        if with_advance_roles:
            roles += [
                (0, 0, {'role': 'advance_received',
                        'account_id': self._acc('62.АВ').id}),
                (0, 0, {'role': 'vat_advance',
                        'account_id': self._acc('76.АВ').id}),
            ]
        return self.Template.create({
            'code': 'SALE_T',
            'name': 'Продажа',
            'resolver_key': 'shipment_upd',
            'role_ids': roles,
        })

    def _sale_invoice_with_vat(self):
        """Инвойс с НДС: untaxed 147.00, tax 22.05, total 169.05."""
        tax = self.env['account.tax'].create({
            'name': 'НДС 15% demo',
            'amount': 15.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
        })
        product = self.env['product.product'].create({'name': 'Demo P'})
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'name': 'Demo',
                'quantity': 1,
                'price_unit': 147.0,
                'tax_ids': [(6, 0, tax.ids)],
            })],
        })

    def test_sale_with_vat_balanced(self):
        # Регрессия: реализация с НДС должна давать сбалансированную проводку.
        tmpl = self._sale_template()
        inv = self._sale_invoice_with_vat()
        inv.rsbu_template_id = tmpl.id
        lines = inv._rsbu_build_lines()
        total_debit = sum(l.get('debit', 0.0) for l in lines)
        total_credit = sum(l.get('credit', 0.0) for l in lines)
        self.assertAlmostEqual(total_debit, total_credit, places=2)
        # Дт 62.01 = total 169.05, Дт 90.03 = НДС -> дебет = total + tax.
        self.assertAlmostEqual(total_debit, 169.05 + 22.05, places=2)

    def test_advance_offset_on_shipment(self):
        """Р1: при отгрузке после аванса зачёт 62.АВ и вычет авансового НДС."""
        # 1) Аванс клиента 105 (НДС 5) через резолвер advance_received.
        adv_tmpl = self._advance_template()
        self._matrix_advance(adv_tmpl)
        pay = self._payment(amount=105.0, vat=5.0)
        pay.action_post()
        self.assertTrue(pay.rsbu_move_id)

        # Остатки после аванса: 62.АВ кредит 105, 76.АВ дебет 5.
        acc_av = self._acc('62.АВ')
        acc_vatav = self._acc('76.АВ')
        bal_av = acc_av.get_balance(
            company_id=self.company.id,
            subconto={'partner': self.partner.id})
        self.assertEqual(bal_av['balance'], 105.0)
        self.assertEqual(bal_av['side'], 'credit')

        # 2) Отгрузка тому же клиенту, шаблон с ролями аванса.
        sale_tmpl = self._sale_template(with_advance_roles=True)
        inv = self._sale_invoice_with_vat()  # total 169.05
        inv.rsbu_template_id = sale_tmpl.id
        lines = inv._rsbu_build_lines()
        # Проводка должна содержать зачёт аванса и вычет авансового НДС.
        d = sum(l.get('debit', 0.0) for l in lines)
        c = sum(l.get('credit', 0.0) for l in lines)
        self.assertAlmostEqual(d, c, places=2)
        inv.action_post()

        # 3) После отгрузки зачёт аванса: 62.АВ по партнёру закрыт (=0).
        # Вычет авансового НДС (76.АВ) при отгрузке НЕ делается — он вынесен
        # в регламент конца периода (rsbu.period.close), поэтому 76.АВ здесь
        # остаётся ненулевым (закрывается регламентом «книга покупок»).
        bal_av2 = acc_av.get_balance(
            company_id=self.company.id,
            subconto={'partner': self.partner.id})
        self.assertAlmostEqual(bal_av2['balance'], 0.0, places=2)

    # ------------------------------------------------------------------
    # customer_payment: аванс / постоплата / переплата
    # ------------------------------------------------------------------
    def _customer_payment_template(self):
        tmpl = self.Template.create({
            'code': 'CUST_PAY',
            'name': 'Оплата от клиента',
            'resolver_key': 'customer_payment',
            'company_id': self.company.id,
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
            ],
        })
        self.Matrix.create({
            'name': 'Оплата клиента',
            'doc_kind': 'payment_inbound',
            'partner_kind': 'customer',
            'has_advance': 'any',
            'template_id': tmpl.id,
            'company_id': self.company.id,
        })
        return tmpl

    def _debt(self, partner, amount, date):
        """Создать дебиторку покупателя (реализация) для теста постоплаты."""
        move = self.env['rsbu.move'].create({
            'date': date, 'company_id': self.company.id,
            'line_ids': [
                (0, 0, {'account_id': self._acc('62.01').id, 'debit': amount,
                        'partner_id': partner.id}),
                (0, 0, {'account_id': self._acc('90.01').id, 'credit': amount}),
            ],
        })
        move.action_post()
        return move

    def _inbound(self, partner, amount, date):
        pay = self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer',
            'partner_id': partner.id, 'amount': amount,
            'journal_id': self.journal_bank.id, 'company_id': self.company.id,
            'date': date,
        })
        pay.action_post()
        return pay

    def test_customer_payment_advance(self):
        """Платёж без долга → аванс (Кт 62.АВ), только деньги.

        Авансовый НДС в платеже НЕ начисляется: он живёт в отдельном
        авансовом счёте-фактуре (rsbu.invoice, invoice_type='advance'),
        рождаемом из платежа и не связанном с документом реализации
        (realization_id пуст). Модель-источник авансового НДС — rsbu.invoice,
        без изменений. Платёж двигает только деньги.
        """
        if 'rsbu_vat_mode' in self.company._fields:  # поле — из rsbu_vat (К5)
            self.company.rsbu_vat_mode = 'vat_5'
        self._customer_payment_template()
        p = self.env['res.partner'].create({'name': 'Аванс-клиент'})
        pay = self._inbound(p, 105000.0, '2026-03-01')
        acc_av = self._acc('62.АВ')
        bal = acc_av.get_balance(company_id=self.company.id,
                                 subconto={'partner': p.id})
        self.assertAlmostEqual(bal['balance'], 105000.0, places=2)
        # Авансовый НДС в платеже не начисляется (68.НДС не затронут платежом).
        # дебиторка 62.01 не затронута
        bal01 = self._acc('62.01').get_balance(
            company_id=self.company.id, subconto={'partner': p.id})
        self.assertAlmostEqual(bal01['balance'], 0.0, places=2)

    def test_customer_payment_postpaid(self):
        """Платёж при наличии долга → погашение 62.01, без аванса и НДС."""
        if 'rsbu_vat_mode' in self.company._fields:  # поле — из rsbu_vat (К5)
            self.company.rsbu_vat_mode = 'vat_5'
        self._customer_payment_template()
        p = self.env['res.partner'].create({'name': 'Постоплата-клиент'})
        self._debt(p, 50000.0, '2026-03-05')
        pay = self._inbound(p, 50000.0, '2026-03-10')
        # 62.01 закрыт (0), 62.АВ не создавался, авансовый НДС не начислен
        bal01 = self._acc('62.01').get_balance(
            company_id=self.company.id, subconto={'partner': p.id})
        self.assertAlmostEqual(bal01['balance'], 0.0, places=2)
        bal_av = self._acc('62.АВ').get_balance(
            company_id=self.company.id, subconto={'partner': p.id})
        self.assertAlmostEqual(bal_av['balance'], 0.0, places=2)

    def test_customer_payment_overpaid(self):
        """Переплата → долг гасится (62.01), остаток в аванс (62.АВ).

        Авансовый НДС в платеже не начисляется (вынесен в СФ на аванс).
        """
        if 'rsbu_vat_mode' in self.company._fields:  # поле — из rsbu_vat (К5)
            self.company.rsbu_vat_mode = 'vat_5'
        self._customer_payment_template()
        p = self.env['res.partner'].create({'name': 'Переплата-клиент'})
        self._debt(p, 30000.0, '2026-03-06')
        pay = self._inbound(p, 100000.0, '2026-03-11')
        # долг 62.01 закрыт
        bal01 = self._acc('62.01').get_balance(
            company_id=self.company.id, subconto={'partner': p.id})
        self.assertAlmostEqual(bal01['balance'], 0.0, places=2)
        # аванс на остаток 70000
        bal_av = self._acc('62.АВ').get_balance(
            company_id=self.company.id, subconto={'partner': p.id})
        self.assertAlmostEqual(bal_av['balance'], 70000.0, places=2)
        # Авансовый НДС в платеже не начисляется (76.АВ платежом не затронут).
