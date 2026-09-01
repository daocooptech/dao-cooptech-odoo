from odoo import _, models

from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @template("ru")
    def _get_ru_template_data(self):
        return {
            "name": _("Chart of Accounts"),
            "code_digits": "1",
            "use_storno_accounting": True,
            "display_invoice_amount_total_words": True,
            "property_account_receivable_id": "ru_acc_62_01",
            "property_account_payable_id": "ru_acc_60_01",
            "property_account_expense_categ_id": "ru_acc_41_01",
            "property_account_income_categ_id": "ru_acc_90_01_1",
        }

    @template("ru", "res.company")
    def _get_ru_res_company(self):
        return {
            self.env.company.id: {
                "account_fiscal_country_id": "base.ru",
                "bank_account_code_prefix": "999",
                "cash_account_code_prefix": "999",
                "transfer_account_code_prefix": "000",
                "income_currency_exchange_account_id": "ru_acc_91_01",
                "expense_currency_exchange_account_id": "ru_acc_91_02",
                "account_journal_early_pay_discount_loss_account_id": "ru_acc_99",
                "account_journal_early_pay_discount_gain_account_id": "ru_acc_99",
                "account_sale_tax_id": "sale_vat_20",
                "account_purchase_tax_id": "purchase_vat_20",
            }
        }

    @template("ru", "account.journal")
    def _get_ru_account_journal(self):
        # В Odoo 19 код журнала обязателен, а имя и тип для кассы шаблон
        # обязан задать сам: раньше Odoo достраивал их по умолчанию, теперь
        # создание падает на ограничении not null.
        return {
            "cash": {
                "name": _("Касса"),
                "type": "cash",
                "code": "КАС",
                "default_account_id": "ru_acc_50_01",
            },
            "bank": {
                "name": _("Расчётный счёт"),
                "type": "bank",
                "code": "БНК",
                "default_account_id": "ru_acc_51",
            },
        }
