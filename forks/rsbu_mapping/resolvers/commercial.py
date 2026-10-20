"""Резолверы коммерческого цикла (по регламенту docs/research/08).

Каждый резолвер получает документ-родитель (account.move / account.payment)
и шаблон rsbu.operation.template (роли счетов). Возвращает список значений
строк rsbu.move.line, сбалансированный по Дт=Кт. Ставка НДС берётся из
инвойса (налоговые строки) либо из поля rsbu_vat_amount платежа.
"""
from .registry import resolver


def _line(account, debit=0.0, credit=0.0, partner=None, product=None,
          user=None, employee=None, name=None, origin=None,
          origin_self=False, contract=None):
    vals = {
        'account_id': account.id,
        'debit': debit,
        'credit': credit,
    }
    if partner:
        vals['partner_id'] = partner.id
    if product:
        vals['product_id'] = product.id
    if user:
        vals['user_id'] = user.id
    if employee:
        vals['employee_id'] = employee.id
    if name:
        vals['name'] = name
    # Субконто «Документ-основание» (аванс): либо явная проводка-основание,
    # либо маркер origin_self (ссылка на саму создаваемую проводку —
    # проставляется миксином после create).
    if origin is not None:
        vals['origin_move_id'] = origin.id
    if origin_self:
        vals['origin_self'] = True
    # Субконто «Договор».
    if contract is not None:
        vals['contract_id'] = contract.id
    return vals


def _doc_contract(doc):
    """Договор документа-источника (partner.contract.customer) или None."""
    return getattr(doc, 'mt_contract_id', False) or None


@resolver('advance_received')
def advance_received(doc, template):
    """Получение аванса от покупателя (входящий платёж).

    Дт bank — Кт advance_received (сумма платежа);
    Дт vat_advance — Кт vat_output (авансовый НДС из rsbu_vat_amount).
    """
    partner = doc.partner_id
    amount = abs(doc.amount)
    vat = abs(getattr(doc, 'rsbu_vat_amount', 0.0) or 0.0)
    contract = _doc_contract(doc)
    bank = template._account('bank')
    advance = template._account('advance_received')
    lines = [
        _line(bank, debit=amount, name='Поступление аванса'),
        # origin_self: аванс ссылается на свою проводку — для дроблёного
        # зачёта по основанию в shipment_upd (get_origin_balances).
        _line(advance, credit=amount, partner=partner, contract=contract,
              origin_self=True, name='Аванс полученный'),
    ]
    if vat:
        vat_advance = template._account('vat_advance')
        vat_output = template._account('vat_output')
        lines += [
            _line(vat_advance, debit=vat, partner=partner,
                  name='НДС с аванса'),
            _line(vat_output, credit=vat, name='НДС с аванса начислен'),
        ]
    return lines


@resolver('advance_refund')
def advance_refund(doc, template):
    """Возврат аванса покупателю.

    Дт advance_received — Кт bank; вычет авансового НДС:
    Дт vat_output — Кт vat_advance.
    """
    partner = doc.partner_id
    amount = abs(doc.amount)
    vat = abs(getattr(doc, 'rsbu_vat_amount', 0.0) or 0.0)
    bank = template._account('bank')
    advance = template._account('advance_received')
    lines = [
        _line(advance, debit=amount, partner=partner, name='Возврат аванса'),
        _line(bank, credit=amount, name='Возврат аванса с р/с'),
    ]
    if vat:
        vat_advance = template._account('vat_advance')
        vat_output = template._account('vat_output')
        lines += [
            _line(vat_output, debit=vat, name='Вычет НДС с аванса'),
            _line(vat_advance, credit=vat, partner=partner,
                  name='Сторно НДС с аванса'),
        ]
    return lines


@resolver('shipment_upd')
def shipment_upd(doc, template):
    """Отгрузка / выполнение работ / УПД (исходящий инвойс).

    Базовая реализация (брутто):
        Дт 62.01 — Кт 90.01 на полную сумму (выручка с НДС);
        Дт 90.03 — Кт 68.НДС на сумму НДС (НДС в составе продаж).

    Дополнительно, если по контрагенту есть незакрытый аванс (кредитовый
    остаток 62.АВ), формируются проводки зачёта аванса и вычета авансового
    НДС (по регламенту 08, ч.1 п.6):
        Дт 62.АВ — Кт 62.01 на сумму зачёта;
        Дт 68.НДС — Кт 76.АВ на авансовый НДС, приходящийся на зачёт.
    """
    partner = doc.partner_id
    company_id = doc.company_id.id
    tax = abs(doc.amount_tax)
    total = abs(doc.amount_total)
    contract = _doc_contract(doc)
    receivable = template._account('receivable')
    revenue = template._account('revenue')

    lines = [
        _line(receivable, debit=total, partner=partner, contract=contract,
              name='Задолженность покупателя'),
        _line(revenue, credit=total, name='Выручка'),
    ]
    if tax:
        revenue_vat = template._account('revenue_vat')
        vat_output = template._account('vat_output')
        lines += [
            _line(revenue_vat, debit=tax, name='НДС с реализации'),
            _line(vat_output, credit=tax, name='НДС с реализации начислен'),
        ]

    # --- Зачёт аванса, ДРОБЛЁННЫЙ по каждому авансу-основанию (FIFO) ---
    # Как в 1С: Дт 62.02 — Кт 62.01 отдельной строкой на каждый аванс,
    # с субконто «Документ-основание» = проводка аванса, в разрезе договора.
    # Вычет авансового НДС здесь НЕ делается — он выполняется регламентом
    # «Формирование записей книги покупок» в конце периода (68.02 — 76.АВ).
    advance = template._account_or_none('advance_received')
    if advance and partner:
        subconto = {'partner': partner.id}
        if contract:
            subconto['contract'] = contract.id
        origins = advance.get_origin_balances(
            date_to=doc.date, company_id=company_id, subconto=subconto)
        remaining = total
        for data in origins:
            if remaining <= 0:
                break
            # 62.02 пассивный: кредитовое сальдо = незакрытый аванс.
            available = data['balance'] if data['side'] == 'credit' else 0.0
            if available <= 0:
                continue
            take = min(available, remaining)
            take = round(take, 2)
            if take <= 0:
                continue
            origin_move = data['origin']
            lines += [
                _line(advance, debit=take, partner=partner, contract=contract,
                      origin=origin_move, name='Зачёт аванса покупателя'),
                _line(receivable, credit=take, partner=partner,
                      contract=contract,
                      name='Зачёт аванса в счёт задолженности'),
            ]
            remaining -= take
    return lines


@resolver('payment_after_shipment')
def payment_after_shipment(doc, template):
    """Постоплата: поступление денег после отгрузки.

    Дт bank — Кт receivable.
    """
    partner = doc.partner_id
    amount = abs(doc.amount)
    bank = template._account('bank')
    receivable = template._account('receivable')
    return [
        _line(bank, debit=amount, name='Оплата от покупателя'),
        _line(receivable, credit=amount, partner=partner,
              name='Погашение задолженности'),
    ]


# Расчётная ставка НДС с аванса по режиму НДС компании (доля налога в сумме).
_ADVANCE_VAT_FRACTION = {
    'vat_5': 5.0 / 105.0,
    'vat_7': 7.0 / 107.0,
}


@resolver('customer_payment')
def customer_payment(doc, template):
    """Поступление денег от покупателя: аванс, постоплата или смешанно.

    Только движение денег (как в 1С; авансовый НДС начисляется отдельным
    документом «Счёт-фактура на аванс», а не здесь). Тип определяется
    сальдо дебиторки 62.01 по контрагенту на дату платежа:

    * есть незакрытая дебиторка → Дт 51 — Кт 62.01 на min(долг, платёж)
      (постоплата, гасит долг по каждому основанию);
    * остаток сверх долга → аванс: Дт 51 — Кт 62.02 с субконто
      «Документ-основание» = сама проводка платежа (origin_self), чтобы
      затем вести зачёт по каждому авансу отдельно.
    """
    partner = doc.partner_id
    company_id = doc.company_id.id
    amount = abs(doc.amount)
    bank = template._account('bank')
    contract = _doc_contract(doc)

    lines = [_line(bank, debit=amount, name='Оплата от покупателя')]

    # Долг покупателя на дату платежа — в разрезе (контрагент, договор),
    # как в 1С (зачёт и погашение ведутся по договору-основанию).
    receivable = template._account_or_none('receivable')
    debt = 0.0
    if receivable and partner:
        subconto = {'partner': partner.id}
        if contract:
            subconto['contract'] = contract.id
        bal = receivable.get_balance(
            date_to=doc.date, company_id=company_id, subconto=subconto)
        # 62.01 активный: дебетовое сальдо = долг покупателя по договору.
        debt = bal['balance'] if bal['side'] == 'debit' else 0.0

    pay_debt = min(debt, amount)
    advance = round(amount - pay_debt, 2)

    # Погашение задолженности (постоплата) — по тому же договору.
    if pay_debt > 0 and receivable:
        lines.append(_line(receivable, credit=pay_debt, partner=partner,
                           contract=contract,
                           name='Погашение задолженности покупателя'))

    # Остаток — аванс (субконто: договор + основание = сама проводка).
    if advance > 0:
        advance_acc = template._account('advance_received')
        lines.append(_line(advance_acc, credit=advance, partner=partner,
                           contract=contract, origin_self=True,
                           name='Аванс полученный'))
    return lines


@resolver('sale_credit_note')
def sale_credit_note(doc, template):
    """Возврат от клиента / кредит-нота (out_refund).

    Сторно реализации: Дт revenue — Кт receivable (сумма без НДС);
    сторно НДС: Дт vat_output — Кт revenue_vat.
    """
    partner = doc.partner_id
    tax = abs(doc.amount_tax)
    total = abs(doc.amount_total)
    receivable = template._account('receivable')
    revenue = template._account('revenue')
    # Зеркально shipment_upd: Дт 90.01 — Кт 62.01 на полную сумму;
    # Дт 68.НДС — Кт 90.03 на сумму НДС (сторно начисления).
    lines = [
        _line(revenue, debit=total, name='Сторно выручки'),
        _line(receivable, credit=total, partner=partner,
              name='Уменьшение задолженности покупателя'),
    ]
    if tax:
        revenue_vat = template._account('revenue_vat')
        vat_output = template._account('vat_output')
        lines += [
            _line(vat_output, debit=tax, name='Сторно НДС с реализации'),
            _line(revenue_vat, credit=tax, name='Сторно НДС в продажах'),
        ]
    return lines


@resolver('purchase_bill')
def purchase_bill(doc, template):
    """Счёт/поступление поставщика (in_invoice).

    Дт expense(26) — Кт payable(60.01) на полную сумму (на УСН входящий
    НДС к вычету не принимается и включается в стоимость).

    Плюс зачёт аванса выданного, ДРОБЛЁННЫЙ по каждому авансу-основанию
    (FIFO) в разрезе договора, как в 1С: Дт 60.01 — Кт 60.02 отдельной
    строкой на каждый аванс (субконто «Документ-основание» = проводка
    аванса).
    """
    partner = doc.partner_id
    company_id = doc.company_id.id
    total = abs(doc.amount_total)
    contract = _doc_contract(doc)
    expense = template._account('expense')
    payable = template._account('payable')

    lines = [
        _line(expense, debit=total, name='Затраты по счёту поставщика'),
        _line(payable, credit=total, partner=partner, contract=contract,
              name='Задолженность перед поставщиком'),
    ]

    # --- Зачёт аванса выданного (60.02), дроблёный по основаниям ---
    advance_paid = template._account_or_none('advance_paid')
    if advance_paid and partner:
        subconto = {'partner': partner.id}
        if contract:
            subconto['contract'] = contract.id
        origins = advance_paid.get_origin_balances(
            date_to=doc.date, company_id=company_id, subconto=subconto)
        remaining = total
        for data in origins:
            if remaining <= 0:
                break
            # 60.02 активный: дебетовое сальдо = незачтённый аванс выданный.
            available = data['balance'] if data['side'] == 'debit' else 0.0
            if available <= 0:
                continue
            take = round(min(available, remaining), 2)
            if take <= 0:
                continue
            origin_move = data['origin']
            lines += [
                _line(payable, debit=take, partner=partner, contract=contract,
                      name='Зачёт аванса выданного'),
                _line(advance_paid, credit=take, partner=partner,
                      contract=contract, origin=origin_move,
                      name='Зачёт аванса в счёт поставки'),
            ]
            remaining -= take
    return lines


@resolver('purchase_credit_note')
def purchase_credit_note(doc, template):
    """Возврат поставщику / кредит-нота поставщика (in_refund).

    Дт payable — Кт expense (сторно затрат и задолженности).
    """
    partner = doc.partner_id
    total = abs(doc.amount_total)
    expense = template._account('expense')
    payable = template._account('payable')
    return [
        _line(payable, debit=total, partner=partner,
              name='Уменьшение задолженности перед поставщиком'),
        _line(expense, credit=total, name='Сторно затрат'),
    ]


@resolver('supplier_payment')
def supplier_payment(doc, template):
    """Оплата поставщику (исходящий платёж): постоплата и/или аванс выданный.

    Зеркально customer_payment. Тип определяется сальдо кредиторки 60.01 по
    (поставщик, договор) на дату платежа:

    * есть незакрытый долг перед поставщиком → Дт 60.01 — Кт 51 на
      min(долг, платёж) (погашение задолженности);
    * остаток сверх долга → аванс выданный: Дт 60.02 — Кт 51 с субконто
      «Документ-основание» = сама проводка платежа (origin_self), договор.
    """
    partner = doc.partner_id
    company_id = doc.company_id.id
    amount = abs(doc.amount)
    bank = template._account('bank')
    payable = template._account('payable')
    contract = _doc_contract(doc)

    # Долг перед поставщиком на дату — в разрезе (поставщик, договор).
    debt = 0.0
    if partner:
        subconto = {'partner': partner.id}
        if contract:
            subconto['contract'] = contract.id
        bal = payable.get_balance(
            date_to=doc.date, company_id=company_id, subconto=subconto)
        # 60.01 пассивный: кредитовое сальдо = наш долг поставщику.
        debt = bal['balance'] if bal['side'] == 'credit' else 0.0

    pay_debt = min(debt, amount)
    advance = round(amount - pay_debt, 2)

    lines = []
    # Погашение задолженности (постоплата).
    if pay_debt > 0:
        lines += [
            _line(payable, debit=pay_debt, partner=partner, contract=contract,
                  name='Оплата поставщику'),
            _line(bank, credit=pay_debt, name='Списание с р/с'),
        ]
    # Остаток — аванс выданный (60.02, origin_self, договор).
    if advance > 0:
        advance_paid = template._account('advance_paid')
        lines += [
            _line(advance_paid, debit=advance, partner=partner,
                  contract=contract, origin_self=True,
                  name='Аванс выданный поставщику'),
            _line(bank, credit=advance, name='Списание с р/с (аванс)'),
        ]
    return lines


@resolver('supplier_refund')
def supplier_refund(doc, template):
    """Возврат денег от поставщика (входящий платёж).

    Дт bank — Кт payable.
    """
    partner = doc.partner_id
    amount = abs(doc.amount)
    payable = template._account('payable')
    bank = template._account('bank')
    return [
        _line(bank, debit=amount, name='Возврат от поставщика'),
        _line(payable, credit=amount, partner=partner,
              name='Уменьшение расчётов с поставщиком'),
    ]
