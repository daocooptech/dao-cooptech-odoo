from odoo import _, fields, models
from odoo.exceptions import UserError

from .coop_vat_regime import NO_VAT_REGIMES, PURCHASE_TAX_BY_REGIME


class AccountMove(models.Model):
    _inherit = 'account.move'

    coop_deal_id = fields.Many2one(
        'coop.deal', string='Сделка', readonly=True, copy=False, index=True)

    def _coop_seller_org(self):
        """Организация-продавец, если счёт выставлен из её компании учёта."""
        self.ensure_one()
        partner = self.company_id.partner_id
        return partner if partner.coop_company_id == self.company_id else partner.browse()

    def _coop_regime(self):
        self.ensure_one()
        org = self._coop_seller_org()
        if not org:
            return False
        return org._coop_vat_regime_at(self.invoice_date or fields.Date.context_today(self))

    def _coop_upd_function(self):
        """Функция УПД по заключению бухгалтера 07.10.2026.

        ДОП — только первичный документ: организация НДС не начисляет, или
        все строки без налога. СЧФДОП — одновременно счёт-фактура: продавец
        плательщик и в счёте есть налог. Счёт не из компании организации
        (платформы) — как было в форке, СЧФДОП.
        """
        self.ensure_one()
        regime = self._coop_regime()
        if not regime:
            return 'СЧФДОП'
        if regime in NO_VAT_REGIMES:
            return 'ДОП'
        taxed = self.invoice_line_ids.tax_ids.filtered(lambda t: t.amount)
        return 'СЧФДОП' if taxed else 'ДОП'

    def _coop_upd_status(self):
        """Статус в печатном УПД: 1 — счёт-фактура и первичный, 2 — первичный."""
        return '2' if self._coop_upd_function() == 'ДОП' else '1'

    def _coop_upd_title(self):
        if self._coop_upd_function() == 'ДОП':
            return ('Документ об отгрузке товаров (выполнении работ), передаче '
                    'имущественных прав (документ об оказании услуг)')
        return ('Счет-фактура и документ об отгрузке товаров (выполнении работ), '
                'передаче имущественных прав (документ об оказании услуг)')

    def _post(self, soft=True):
        for move in self.filtered(lambda m: m.is_sale_document()):
            org = move._coop_seller_org()
            if not org:
                continue
            regime = move._coop_regime()
            if not regime:
                raise UserError(_(
                    'У организации «%s» не указан режим НДС на дату счёта. '
                    'Без него неясно, счёт-фактура это или только первичный '
                    'документ.') % org.name)
            # Освобождённый от НДС, выставивший налог, обязан его уплатить
            # (п. 5 ст. 173 НК) — из своих денег. Такой счёт не проводим.
            if regime in NO_VAT_REGIMES and move.invoice_line_ids.tax_ids.filtered('amount'):
                raise UserError(_(
                    'Организация «%s» не начисляет НДС, а в счёте есть строка с '
                    'налогом. Уберите налог: выставленный НДС пришлось бы '
                    'уплатить в бюджет.') % org.name)
        return super()._post(soft)

    def _coop_bill_vals(self):
        """Входящий документ покупателя-организации по этому УПД.

        Покупатель отражает документ таким, каким его получил: те же
        строки и та же ставка, что выставил продавец, в своей компании
        учёта и с продавцом как поставщиком.
        """
        self.ensure_one()
        buyer = self.partner_id.commercial_partner_id
        company = buyer._coop_ensure_company()
        tax = self.env['account.chart.template'].with_company(company).ref(
            PURCHASE_TAX_BY_REGIME[self._coop_regime()])
        return {
            'move_type': 'in_invoice',
            'company_id': company.id,
            'partner_id': self._coop_seller_org().id,
            'invoice_date': self.invoice_date,
            'ref': self.name,
            'coop_deal_id': self.coop_deal_id.id,
            'invoice_line_ids': [(0, 0, {
                'name': line.name,
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'tax_ids': [(6, 0, tax.ids)],
            }) for line in self.invoice_line_ids],
        }

    def _coop_form_action(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }
