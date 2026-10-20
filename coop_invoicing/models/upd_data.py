# -*- coding: utf-8 -*-
"""Данные счёта, без которых УПД не собирается (задача 298).

Кроме реквизитов сторон УПД требует от счёта договор, лицо,
ответственное за передачу, грузоотправителя и грузополучателя и код
ОКЕИ у каждой строки. На платформе всё это уже есть в сделке:

- договор — сама сделка: её номер и дата подписания;
- передаёт товар тот, кто вправе подписывать за продавца («Подпись»);
- грузоотправитель — продавец, грузополучатель — покупатель;
- единица строки — единица строки сделки («шт.», «мес.», «усл.»).
"""
from datetime import timedelta

from odoo import api, fields, models

# Единица строки сделки → единица движка. Строка сделки хранит её
# текстом, как её написал продавец.
UOM_BY_NAME = {
    'шт.': 'uom.product_uom_unit', 'шт': 'uom.product_uom_unit',
    'мес.': 'coop_invoicing.uom_month', 'мес': 'coop_invoicing.uom_month',
    'усл.': 'coop_invoicing.uom_service', 'усл. ед.': 'coop_invoicing.uom_service',
    'ч': 'uom.product_uom_hour', 'ч.': 'uom.product_uom_hour',
    'дн.': 'uom.product_uom_day', 'сут.': 'uom.product_uom_day',
    'кг': 'uom.product_uom_kgm', 'т': 'uom.product_uom_ton',
    'л': 'uom.product_uom_litre', 'м': 'uom.product_uom_meter',
    'м²': 'uom.product_uom_square_meter', 'м³': 'uom.product_uom_cubic_meter',
}
# Без единицы: работа и услуга считаются условными единицами, вещь — штуками.
SERVICE_WAYS = ('service', 'job')


class CoopDeal(models.Model):
    _inherit = 'coop.deal'

    def _coop_upd_uom(self, uom_name=None):
        self.ensure_one()
        xmlid = UOM_BY_NAME.get((uom_name or '').strip().lower())
        if not xmlid:
            xmlid = 'coop_invoicing.uom_service' if self.way in SERVICE_WAYS \
                else 'uom.product_uom_unit'
        return self.env.ref(xmlid)

    def _coop_upd_contract(self, company, buyer):
        """Договор по сделке в компании продавца: завести, если его нет."""
        self.ensure_one()
        Contract = self.env['partner.contract.customer'].sudo()
        contract = Contract.search([('company_id', '=', company.id),
                                    ('name', '=', self.number)], limit=1)
        if contract:
            return contract
        start = self.signed_on or fields.Date.to_date(self.create_date)
        buyer = buyer.commercial_partner_id
        if not buyer.is_company:
            kind = 'person'
        elif len(buyer.inn or '') == 12:
            kind = 'company_ip'
        else:
            kind = 'company'
        contract = Contract.create({
            'date_start': start,
            'date_end': start + timedelta(days=365),
            'type': 'customer',
            'profile_id': self.env.ref('coop_invoicing.contract_profile_deal').id,
            'partner_id': buyer.id,
            'partner_type': kind,
            'company_id': company.id,
            'state': 'signed',
            'signed': True,
        })
        # Модуль договоров при создании ставит номер из своей нумерации;
        # номер договора по сделке — номер сделки.
        contract.name = self.number
        return contract

    def _coop_upd_kladov(self, company):
        """Кто передал товар: подписант продавца, иначе руководитель компании."""
        self.ensure_one()
        signer = self.coop_seller_id.sudo().coop_member_ids.filtered(
            lambda m: m.state != 'ended' and 'sign' in m.power_ids.mapped('code'))[:1]
        user = signer and self.env['res.users'].sudo().search(
            [('partner_id', '=', signer.partner_id.id)], limit=1)
        return user or company.chief_id

    def _coop_upd_vals(self, company, buyer):
        """Поля счёта для УПД — при выставлении и при дозаполнении."""
        self.ensure_one()
        return {
            'mt_contract_id': self._coop_upd_contract(company, buyer).id,
            'kladov': self._coop_upd_kladov(company).id,
            'gruzootpr': self.coop_seller_id.id,
            'gruzopol': buyer.commercial_partner_id.id,
        }


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def _coop_fill_upd_data(self):
        """Дозаполнить данные УПД у счетов по сделкам, выставленных раньше.

        Только пустое: договор, ответственный, грузоотправитель и
        получатель, единица строки. Суммы и проводки не трогаются, поэтому
        проведённый счёт остаётся проведённым.
        """
        moves = self.sudo().search([('coop_deal_id', '!=', False),
                                    ('move_type', '=', 'out_invoice')])
        filled = 0
        for move in moves:
            deal = move.coop_deal_id
            if move.mt_contract_id and move.mt_contract_id.name != deal.number:
                move.mt_contract_id.name = deal.number
            values = {}
            if not (move.mt_contract_id and move.kladov and move.gruzootpr and move.gruzopol):
                values = {key: value for key, value in deal._coop_upd_vals(
                    move.company_id, move.partner_id).items() if not move[key]}
            if values:
                move.write(values)
                filled += 1
            deal_lines = deal.line_ids.filtered('price_unit')
            for index, line in enumerate(move.invoice_line_ids):
                if line.product_uom_id:
                    continue
                source = deal_lines[index] if index < len(deal_lines) else False
                line.product_uom_id = deal._coop_upd_uom(source and source.uom_name)
        return filled
