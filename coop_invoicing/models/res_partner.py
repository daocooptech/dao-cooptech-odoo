from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .coop_vat_regime import PURCHASE_TAX_BY_REGIME, SALE_TAX_BY_REGIME, VAT_REGIMES


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_vat_regime_ids = fields.One2many(
        'coop.vat.regime', 'organization_id', string='Режим НДС')
    coop_vat_regime = fields.Selection(
        VAT_REGIMES, string='Режим НДС сейчас', compute='_compute_coop_vat_regime')
    coop_can_edit_vat = fields.Boolean(compute='_compute_coop_can_edit_vat')
    # Своя компания Odoo для учёта организации. Заводится при первом
    # счёте, а не у всех сразу: у дара и обмена бухгалтерии нет, и
    # пустой план счетов на триста с лишним строк ничего не показывает.
    coop_company_id = fields.Many2one(
        'res.company', string='Компания учёта', readonly=True, copy=False, index=True)

    @api.depends('coop_vat_regime_ids.date_from', 'coop_vat_regime_ids.regime')
    def _compute_coop_vat_regime(self):
        today = fields.Date.context_today(self)
        for partner in self:
            partner.coop_vat_regime = partner._coop_vat_regime_at(today)

    @api.depends_context('uid')
    def _compute_coop_can_edit_vat(self):
        treasury = self.env.user.coop_treasury_partner_ids
        for partner in self:
            partner.coop_can_edit_vat = partner.is_company and partner in treasury

    def _coop_vat_regime_at(self, date):
        """Код режима НДС на дату или False, если режим не задан."""
        self.ensure_one()
        date = fields.Date.to_date(date)
        regimes = self.sudo().coop_vat_regime_ids.filtered(
            lambda r: r.date_from <= date).sorted('date_from', reverse=True)
        return regimes[:1].regime or False

    def _coop_ensure_company(self):
        """Компания учёта организации: завести, если её ещё нет.

        Под sudo: заводит её человек с полномочием «Бухгалтерия и счета»,
        а создавать компании и грузить план счетов участнику не положено.
        Карточка организации остаётся общей: движок при создании компании
        из готовой карточки её `company_id` не трогает, и в каталоге
        организация видна всем, как и была.
        """
        self.ensure_one()
        if not self.is_company:
            raise UserError(_('Компания учёта заводится только у организации.'))
        if self.coop_company_id:
            return self.coop_company_id
        org = self.sudo()
        company = self.env['res.company'].sudo().create({
            'name': org.name,
            'partner_id': org.id,
            'currency_id': self.env.ref('base.RUB').id,
            'country_id': self.env.ref('base.ru').id,
        })
        self.env['account.chart.template'].sudo().try_loading(
            'ru', company=company, install_demo=False)
        company._coop_prepare_taxes()
        org.coop_company_id = company
        self.env['res.users']._coop_sync_accounting_access(org)
        return company

    def _coop_sale_tax_at(self, date):
        """Налог строки продажи по режиму организации на дату."""
        self.ensure_one()
        regime = self._coop_vat_regime_at(date)
        if not regime:
            raise UserError(_(
                'У организации «%s» не указан режим НДС на %s. Его указывает '
                'тот, у кого есть полномочие «Бухгалтерия и счета», на '
                'карточке организации.'
            ) % (self.name, fields.Date.to_string(date)))
        company = self._coop_ensure_company()
        return self.env['account.chart.template'].with_company(company).ref(
            SALE_TAX_BY_REGIME[regime])


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _coop_prepare_taxes(self):
        """Налоги организации: цены в сделках — с налогом.

        В сделке сумма — то, что покупатель платит; график платежей
        складывается в неё же. Счёт должен выйти на ту же сумму, поэтому
        налоги считаются «в том числе» — и у продавца, и у покупателя. Ставки 5 % и 7 % в плане
        счетов `ru` выключены — у организации на УСН с НДС они нужны.
        """
        Chart = self.env['account.chart.template']
        for company in self:
            taxes = self.env['account.tax']
            for code in set(SALE_TAX_BY_REGIME.values()) | set(PURCHASE_TAX_BY_REGIME.values()):
                taxes |= Chart.with_company(company).ref(code, raise_if_not_found=False) \
                    or self.env['account.tax']
            taxes.sudo().with_context(active_test=False).write({
                'active': True,
                'price_include_override': 'tax_included',
            })
