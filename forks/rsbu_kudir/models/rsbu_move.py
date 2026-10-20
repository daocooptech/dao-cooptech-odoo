from odoo import fields, models



class RsbuMove(models.Model):
    """Расширение операции: перенос правила признания УСН (для КУДиР)."""
    _inherit = 'rsbu.move'

    usn_recognition = fields.Selection(
        selection=[
            ('income', 'Доход'),
            ('expense', 'Расход'),
            ('refund_customer', 'Возврат клиенту'),
            ('refund_supplier', 'Возврат поставщику'),
            ('none', 'Не участвует в УСН'),
        ],
        string='Признание в УСН', default='none', copy=False)
    is_refund = fields.Boolean(string='Это возврат', copy=False)
    kudir_income_vat = fields.Monetary(
        string='НДС, исключаемый из дохода УСН',
        currency_field='currency_id', default=0.0, copy=False,
        help='Сумма предъявленного НДС по поступлению, которая исключается '
             'из дохода КУДиР (доход = поступление − этот НДС). На УСН+НДС '
             'заполняется из налога документа; для необлагаемых операций 0.')
    kudir_income_adjust = fields.Monetary(
        string='Корректировка дохода УСН при отгрузке',
        currency_field='currency_id', default=0.0, copy=False,
        help='Отрицательная корректировка дохода КУДиР в момент отгрузки в '
             'счёт ранее полученного аванса, по которому НДС не был исключён '
             'при поступлении (переходящая сделка: аванс получен до перехода '
             'на НДС, отгрузка облагается по ставке). Равна −(зачтённый аванс '
             '× расчётная ставка НДС). См. п.1 ст.248, п.1 ст.346.15 НК РФ.')


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _rsbu_is_calibration(self):
        """Документ создан калибровкой (несёт ключ 1С). Для таких проводок
        поля КУДиР-НДС размечает калибровочный слой по ОСВ-эталону, а не
        онлайн-логика проведения."""
        self.ensure_one()
        return bool(getattr(self, 'calibration_ref_key', False))

    def _rsbu_get_move_values(self):
        vals = super()._rsbu_get_move_values()
        template = self.rsbu_template_id or self._rsbu_detect_template()
        if template:
            vals['usn_recognition'] = template.usn_recognition
            vals['is_refund'] = template.is_refund
            # Корректировка дохода КУДиР при отгрузке в счёт аванса, по
            # которому НДС не был исключён при поступлении (переходящая
            # сделка УСН→УСН+НДС). Только для облагаемой отгрузки.
            # Калибровочные отгрузки размечаются mark_kudir_shipment_adjust
            # (по ОСВ-эталону входящих авансов) — онлайн-расчёт пропускаем.
            if template.resolver_key == 'shipment_upd' and self.amount_tax \
                    and not self._rsbu_is_calibration():
                adjust = self._rsbu_kudir_shipment_adjust(template)
                if adjust:
                    vals['kudir_income_adjust'] = adjust
        return vals

    def _rsbu_kudir_shipment_adjust(self, template):
        """Отрицательная корректировка дохода КУДиР при отгрузке.

        Проходит зачитываемые отгрузкой авансы (FIFO по основанию, как в
        резолвере shipment_upd). Для авансов, по которым НДС не был исключён
        при поступлении (origin.kudir_income_vat == 0), начисляет исключение
        сейчас: −(зачтённая сумма × расчётная доля НДС). Возвращает <= 0.
        """
        self.ensure_one()
        fraction = self.company_id._rsbu_vat_fraction_at(self._rsbu_move_date())
        if not fraction:
            return 0.0
        advance = template.sudo()._account_or_none('advance_received')
        partner = self.partner_id
        if not advance or not partner:
            return 0.0
        subconto = {'partner': partner.id}
        contract = getattr(self, 'mt_contract_id', False)
        if contract:
            subconto['contract'] = contract.id
        origins = advance.get_origin_balances(
            date_to=self.date, company_id=self.company_id.id,
            subconto=subconto)
        remaining = abs(self.amount_total)
        corr_base = 0.0
        for data in origins:
            if remaining <= 0:
                break
            available = data['balance'] if data['side'] == 'credit' else 0.0
            if available <= 0:
                continue
            take = round(min(available, remaining), 2)
            if take <= 0:
                continue
            origin_move = data['origin']
            # НДС по этому авансу при поступлении не исключался → исключаем
            # соответствующую долю сейчас, при отгрузке.
            if not (origin_move.kudir_income_vat or 0.0):
                corr_base += take
            remaining -= take
        if corr_base <= 0:
            return 0.0
        return -round(corr_base * fraction, 2)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _rsbu_is_calibration(self):
        """См. AccountMove._rsbu_is_calibration."""
        self.ensure_one()
        return bool(getattr(self, 'calibration_ref_key', False))

    def _rsbu_get_move_values(self):
        vals = super()._rsbu_get_move_values()
        template = self.rsbu_template_id or self._rsbu_detect_template()
        if template:
            vals['usn_recognition'] = template.usn_recognition
            vals['is_refund'] = template.is_refund
            # НДС, исключаемый из дохода КУДиР (доход = поступление − НДС).
            # Только для доходных поступлений от покупателя (кассовый метод
            # УСН, п.1 ст.248/346.15 НК: доход без предъявленного НДС).
            # Калибровочные проводки размечаются отдельно (mark_kudir_vat по
            # ОСВ-эталону) — онлайн-расчёт для них пропускаем.
            if template.usn_recognition == 'income' \
                    and not self._rsbu_is_calibration():
                vals['kudir_income_vat'] = self._rsbu_kudir_income_vat()
        return vals

    def _rsbu_kudir_income_vat(self):
        """НДС, исключаемый из дохода КУДиР по клиентскому поступлению.

        Приоритет — явно указанный НДС платежа (rsbu_vat_amount: банковская
        выписка/оператор). Иначе, если поступление относится к облагаемой
        НДС реализации (инвойс того же контрагента и договора несёт налог —
        «инвойс источник правды»), исключаем расчётную долю НДС из суммы.
        Для необлагаемых операций (лицензии и т.п.) — 0.
        """
        self.ensure_one()
        vat = abs(self.rsbu_vat_amount or 0.0)
        if vat:
            return round(vat, 2)
        fraction = self.company_id._rsbu_vat_fraction_at(self._rsbu_move_date())
        if fraction and self._rsbu_payment_is_taxable():
            return round(abs(self.amount) * fraction, 2)
        return 0.0

    def _rsbu_payment_is_taxable(self):
        """Облагается ли НДС реализация, к которой относится поступление.

        Инвойс — источник правды об облагаемости: ищем out_invoice того же
        контрагента и договора (mt_contract_id) с ненулевым налогом. Договор
        в смешанной сделке (лицензия без НДС + услуги с НДС) разграничивает
        облагаемость по конкретной реализации.
        """
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return False
        Move = self.env['account.move'].sudo()
        domain = [
            ('move_type', '=', 'out_invoice'),
            ('company_id', '=', self.company_id.id),
            ('partner_id', '=', partner.id),
            ('amount_tax', '>', 0),
        ]
        contract = getattr(self, 'mt_contract_id', False)
        if contract:
            domain.append(('mt_contract_id', '=', contract.id))
        return bool(Move.search(domain, limit=1))
