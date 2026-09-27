import logging

from odoo import _, models

from odoo.addons.account.models.chart_template import template

_logger = logging.getLogger(__name__)


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
                "account_journal_early_pay_discount_loss_account_id": "ru_acc_91_02",
                "account_journal_early_pay_discount_gain_account_id": "ru_acc_91_01",
                "account_sale_tax_id": "sale_vat_22",
                "account_purchase_tax_id": "purchase_vat_22",
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

    def _coop_ru_refresh(self):
        """Довести план счетов уже созданных компаний до шаблона.

        Правка шаблона 28.09.2026 (решение 427, заключение бухгалтера
        «Паевой фонд по видам кооперативов и правка плана счетов l10n_ru»):
        у счетов капитала, фондов и расчётов стоял тип «расход» — они
        обнулялись бы 1 января, паевой фонд уходил в отчёт о прибылях; НДС
        20 % вместо 22 %; у налогов не было счетов распределения.

        Перезагрузка шаблона (`try_loading`) заводит новые счета и налоги,
        но у существующих счетов обновляет только теги, а налоги компании
        по умолчанию не трогает. Остальное — здесь. Счёт, по которому уже
        есть проводки, не трогаем и пишем в журнал.
        """
        chart = self.sudo()
        companies = self.env['res.company'].sudo().search([('chart_template', '=', 'ru')])
        for company in companies:
            chart.try_loading('ru', company, install_demo=False)
            chart = chart.with_company(company)
            Line = self.env['account.move.line'].sudo()
            ctx = {'active_test': False, 'tracking_disable': True}
            data = chart._get_chart_template_model_data('ru', 'account.account')
            changed = skipped = 0
            for xmlid, values in data.items():
                account = self.env.ref(chart.company_xmlid(xmlid, company), raise_if_not_found=False)
                if not account:
                    continue
                account = account.sudo().with_company(company).with_context(**ctx)
                if Line.search_count([('account_id', '=', account.id)], limit=1):
                    skipped += 1
                    _logger.warning('План счетов: у счёта %s есть проводки — не трогаю', account.code)
                    continue
                vals = {key: values[key] for key in ('code', 'account_type', 'reconcile', 'active')
                        if key in values}
                if values.get('name'):
                    vals['name'] = values['name']
                current = {key: account[key] for key in vals}
                if current != vals:
                    account.write(vals)
                    changed += 1
                if values.get('name@ru_RU') and account.with_context(lang='ru_RU').name != values['name@ru_RU']:
                    account.with_context(lang='ru_RU').name = values['name@ru_RU']

            # Счета распределения у налогов, заведённых до правки шаблона.
            tax_data = chart._get_chart_template_model_data('ru', 'account.tax')
            for xmlid, values in tax_data.items():
                tax = self.env.ref(chart.company_xmlid(xmlid, company), raise_if_not_found=False)
                if not tax:
                    continue
                tax = tax.sudo().with_context(**ctx)
                accounts = [cmd[2].get('account_id') for cmd in values.get('repartition_line_ids', [])
                            if isinstance(cmd, (list, tuple)) and len(cmd) > 2
                            and isinstance(cmd[2], dict) and cmd[2].get('repartition_type') == 'tax']
                target = next((a for a in accounts if a), None)
                if target:
                    account = self.env.ref(chart.company_xmlid(target, company), raise_if_not_found=False)
                    lines = tax.repartition_line_ids.filtered(
                        lambda line: line.repartition_type == 'tax' and not line.account_id)
                    if account and lines:
                        lines.write({'account_id': account.id})
                tax_vals = {}
                if 'active' in values and tax.active != values['active']:
                    tax_vals['active'] = values['active']
                if values.get('name@ru_RU') and tax.with_context(lang='ru_RU').name != values['name@ru_RU']:
                    tax.with_context(lang='ru_RU').name = values['name@ru_RU']
                if tax_vals:
                    tax.write(tax_vals)

            ref = lambda xmlid: self.env.ref(chart.company_xmlid(xmlid, company), raise_if_not_found=False)
            company_vals = {}
            for field, xmlid in (('account_sale_tax_id', 'sale_vat_22'),
                                 ('account_purchase_tax_id', 'purchase_vat_22'),
                                 ('account_journal_early_pay_discount_loss_account_id', 'ru_acc_91_02'),
                                 ('account_journal_early_pay_discount_gain_account_id', 'ru_acc_91_01')):
                record = ref(xmlid)
                if record and company[field] != record:
                    company_vals[field] = record.id
            if company_vals:
                company.sudo().write(company_vals)

            # Товары со старым НДС 20 % — на 22 %.
            for old_x, new_x, field in (('sale_vat_20', 'sale_vat_22', 'taxes_id'),
                                        ('purchase_vat_20', 'purchase_vat_22', 'supplier_taxes_id')):
                old, new = ref(old_x), ref(new_x)
                if not old or not new:
                    continue
                products = self.env['product.template'].sudo().with_context(**ctx).search([(field, 'in', old.ids)])
                for product in products:
                    product[field] = [(3, old.id), (4, new.id)]
            _logger.info('План счетов «%s»: счетов изменено %s, пропущено с проводками %s',
                         company.name, changed, skipped)
        return True
