# -*- coding: utf-8 -*-
"""Режимы НДС организаций и счета по сделкам (решение 449, НВ15).

Режим — у каждой организации-участника, по жребию от её номера (свой
жребий: с общим генератором повторный прогон перекидывал бы режимы).
Разброс — как на живой площадке: большинство на упрощёнке ниже порога и
освобождено от НДС, часть на АУСН, часть на УСН с НДС 5 % или 7 %, часть
на общем режиме; у некоторых с июля режим сменился после превышения
порога в 20 млн ₽; у немногих режим не указан — так виден и отказ
выставить счёт, пока он не задан.

Счета — по исполняемым и завершённым сделкам продажи, услуг и работ, где
продавец организация с режимом: в её компании учёта, во всех состояниях
(черновик, проведён, оплачен целиком или частично, отменён); у
покупателя-организации — входящий документ в его компании. Прогон
повторяемый: режим не трогается, если у организации он уже есть, счёт —
если у сделки он уже выставлен.
"""
import logging
import random
from datetime import date

_logger = logging.getLogger(__name__)

YEAR_START = date(2026, 1, 1)


def _regimes_for(rnd):
    """Список (с даты, режим, основание) для одной организации."""
    roll = rnd.random()
    if roll < 0.03:
        return []
    if roll < 0.50:
        return [(YEAR_START, 'exempt_145', 'УСН, доход за 2025 год до 20 млн ₽')]
    if roll < 0.60:
        return [(YEAR_START, 'not_payer', 'АУСН')]
    if roll < 0.72:
        return [(YEAR_START, 'usn_5', 'Уведомление о ставке 5 %')]
    if roll < 0.77:
        return [(YEAR_START, 'usn_7', 'Уведомление о ставке 7 %')]
    if roll < 0.92:
        return [(date(2025, 1, 1), 'general_22', 'Общий режим')]
    # Превышение порога в июне: НДС с 1 июля (п. 5 ст. 145 НК).
    return [(YEAR_START, 'exempt_145', 'УСН, доход за 2025 год до 20 млн ₽'),
            (date(2026, 7, 1), 'usn_5', 'Доход превысил 20 млн ₽ в июне 2026')]


def load_vat_regimes(env):
    Partner = env['res.partner'].sudo()
    Regime = env['coop.vat.regime'].sudo()
    orgs = Partner.search([
        ('is_company', '=', True), ('coop_is_participant', '=', True),
        ('coop_vat_regime_ids', '=', False)], order='id')
    rows = []
    for org in orgs:
        rnd = random.Random(20261007 + org.id)
        rows += [{'organization_id': org.id, 'date_from': day, 'regime': regime, 'note': note}
                 for day, regime, note in _regimes_for(rnd)]
    if rows:
        Regime.create(rows)
    _logger.info('Режимы НДС: заведены у %s организаций', len(orgs))
    return len(orgs)


def load_invoices(env):
    """Счета по сделкам: у продавца — УПД, у покупателя — входящий документ.

    Берутся все подходящие сделки: исполняемые и завершённые продажи,
    услуги, работы и аренда, где продавец — организация с режимом НДС.
    Частные лица счетов-фактур и УПД не выставляют, поэтому их сделки
    остаются с одним актом.
    """
    if 'coop.vat.regime' not in env:
        return 0
    Deal = env['coop.deal'].sudo()
    Move = env['account.move'].sudo()
    for company in env['res.partner'].sudo().search([('coop_company_id', '!=', False)]).coop_company_id:
        company._coop_prepare_taxes()
    deals = Deal.search([
        ('state', 'in', ('active', 'acceptance', 'done')),
        ('way', 'in', ('sale', 'purchase', 'batch', 'rent', 'service', 'job')),
        ('amount', '>', 0),
    ], order='id')
    made = bills = 0
    for deal in deals:
        if deal.coop_invoice_ids.filtered(lambda m: m.move_type == 'out_invoice'):
            continue
        seller = deal.coop_seller_id
        if not seller.is_company:
            continue
        shipped = deal._coop_shipped_on()
        if not seller._coop_vat_regime_at(shipped):
            continue
        rnd = random.Random(20261008 + deal.id)
        company = seller._coop_ensure_company()
        move = Move.with_company(company).create(deal._coop_invoice_vals(shipped))
        made += 1
        # Состояние счёта — по ходу сделки: по исполняемой счёт часто ещё
        # черновик, по завершённой проведён и оплачен настолько, насколько
        # оплачена сделка; изредка отменён — выставили не на ту сумму.
        roll = rnd.random()
        if deal.state == 'active' and roll < 0.6:
            continue
        if roll < 0.08:
            move.button_cancel()
            continue
        move.action_post()
        paid = sum(deal.payment_ids.filtered(lambda p: p.state == 'paid').mapped('amount'))
        bill = Move.browse()
        buyer = move.partner_id.commercial_partner_id
        # Покупатель-организация с режимом НДС отражает полученный УПД у
        # себя — как сделал бы его бухгалтер.
        if buyer.is_company and buyer.coop_is_participant and buyer._coop_vat_regime_at(shipped)                 and rnd.random() < 0.85:
            buyer_company = buyer._coop_ensure_company()
            buyer_company._coop_prepare_taxes()
            bill = Move.with_company(buyer_company).create(move._coop_bill_vals())
            bill.action_post()
            bills += 1
        if paid > 0:
            amount = min(paid, move.amount_total)
            when = max(deal.payment_ids.filtered(lambda p: p.state == 'paid').mapped('paid_on')
                       or [move.invoice_date])
            _register_payment(env, move, amount, max(when, move.invoice_date))
            if bill:
                _register_payment(env, bill, amount, max(when, bill.invoice_date))
    env['res.users']._coop_sync_accounting_access()
    _logger.info('Счета по сделкам: УПД выставлено %s, входящих у покупателей %s, компаний учёта %s',
                 made, bills,
                 env['res.partner'].sudo().search_count([('coop_company_id', '!=', False)]))
    return made


def _register_payment(env, move, amount, when):
    """Оплата документа — на сумму, реально оплаченную по сделке."""
    try:
        with env.cr.savepoint():
            env['account.payment.register'].sudo().with_company(move.company_id).with_context(
                active_model='account.move', active_ids=move.ids,
            ).create({'payment_date': when, 'amount': amount})._create_payments()
    except Exception as error:  # noqa: BLE001
        # Оплата — украшение витрины: без неё документ остаётся проведённым.
        _logger.warning('Оплата %s не записана: %s', move.name, error)
