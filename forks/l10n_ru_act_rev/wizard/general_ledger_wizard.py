import logging
import time
from ast import literal_eval
from odoo import _, api, fields, models
from odoo.tools import date_utils,pycompat
from pytils import dt,numeral
from datetime import datetime, date
import re
import urllib
from odoo.exceptions import UserError

class GeneralLedgerReportWizard(models.TransientModel):
    """General ledger report wizard."""

    _name = "general.ledger.act_revise.wizard"
    _description = "General Ledger Report Wizard"
    _inherit = "act_revise.abstract_wizard"

    # date_range_id = fields.Many2one(comodel_name="date.range", string="Date range")
    date_from = fields.Date(string="Начало даты", required=True, default=lambda self: self._init_date_from())
    date_to = fields.Date(string="Конец даты", required=True, default=fields.Date.context_today)
    fy_start_date = fields.Date(compute="_compute_fy_start_date")
    target_move = fields.Selection(
        [("posted", "Все проведенные проводки"), ("all", "Все проводки")],
        string="Цель операции",
        required=True,
        default="posted",
    )
    account_ids = fields.Many2many(
        comodel_name="account.account", string=_("Filter accounts")
    )
    centralize = fields.Boolean(string=_("Activate centralization"), default=True)
    hide_account_at_0 = fields.Boolean(
        string=_("Hide account ending balance at 0"),
        help=_("Use this filter to hide an account or a partner "
        "with an ending balance at 0. "
        "If partners are filtered, "
        "debits and credits totals will not match the trial balance."),
    )
    receivable_accounts_only = fields.Boolean()
    payable_accounts_only = fields.Boolean()
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string=_("Filter partners"),
        default=lambda self: self._default_partners(),
    )
    account_journal_ids = fields.Many2many(
        comodel_name="account.journal", string=_("Filter journals")
    )
    cost_center_ids = fields.Many2many(
        comodel_name="account.analytic.account", string=_("Filter cost centers")
    )

    not_only_one_unaffected_earnings_account = fields.Boolean(readonly=True)
    foreign_currency = fields.Boolean(
        string=_("Show foreign currency"),
        help=_("Display foreign currency for move lines, unless "
        "account currency is not setup through chart of accounts "
        "will display initial and final balance in that currency."),
        default=lambda self: self._default_foreign_currency(),
    )
    account_code_from = fields.Many2one(
        comodel_name="account.account",
        help="Starting account in a range",
    )
    account_code_to = fields.Many2one(
        comodel_name="account.account",
        help="Ending account in a range",
    )
    grouped_by = fields.Selection(
        selection=[("", "None"), ("partners", "Partners"), ("taxes", "Taxes")],
        default="partners",
    )
    show_cost_center = fields.Boolean(
        string="Show Analytic Account",
        default=True,
    )
    domain = fields.Char(
        string="Journal Items Domain",
        default=[],
        help="This domain will be used to select specific domain for Journal " "Items",
    )

    # def _print_report(self, report_type):
    #     self.ensure_one()
    #     data = self._prepare_report_general_ledger()
    #     report = self.env["ir.actions.report"].search(
    #         [("report_name", "=", "act_revise.general_ledger"), ("report_type", "=", report_type)], limit=1, )
    #     if self.partner_ids[0].parent_id:
    #         partner = int(self.partner_ids[0].parent_id.id)
    #     else:
    #         partner = int(self.partner_ids[0].id)
    #     return {
    #         'type': 'ir.actions.act_url',
    #         'url': '/my/act_revise_contact/%s?date_to=%s&date_from=%s&target_move=%s&company=%s&partner=%s' % (
    #             urllib.parse.quote(self.get_report_filename()), self.date_to, self.date_from, self.target_move,
    #             self.company_id.id, partner),
    #         'target': 'new',
    #     }

    def _get_account_move_lines_domain(self):
        domain = literal_eval(self.domain) if self.domain else []
        return domain

    @api.onchange("account_code_from", "account_code_to")
    def on_change_account_range(self):
        if (
            self.account_code_from
            and self.account_code_from.code.isdigit()
            and self.account_code_to
            and self.account_code_to.code.isdigit()
        ):
            start_range = self.account_code_from.code
            end_range = self.account_code_to.code
            self.account_ids = self.env["account.account"].search(
                [("code", ">=", start_range), ("code", "<=", end_range)]
            )
            if self.company_id:
                self.account_ids = self.account_ids.filtered(
                    lambda a: a.company_ids == self.company_id
                )

    def _init_date_from(self):
        """set start date to begin of current year if fiscal year running"""
        today = fields.Date.context_today(self)
        company = self.company_id or self.env.company
        last_fsc_month = company.fiscalyear_last_month
        last_fsc_day = company.fiscalyear_last_day

        if (
            today.month < int(last_fsc_month)
            or today.month == int(last_fsc_month)
            and today.day <= last_fsc_day
        ):
            return time.strftime("%Y-01-01")
        else:
            return False

    def _default_foreign_currency(self):
        return self.env.user.has_group("base.group_multi_currency")

    @api.depends("date_from")
    def _compute_fy_start_date(self):
        for wiz in self:
            if wiz.date_from:
                date_from, date_to = date_utils.get_fiscal_year(
                    wiz.date_from,
                    day=self.company_id.fiscalyear_last_day,
                    month=int(self.company_id.fiscalyear_last_month),
                )
                wiz.fy_start_date = date_from
            else:
                wiz.fy_start_date = False

    @api.onchange("company_id")
    def onchange_company_id(self):
        """Handle company change."""
        count = self.env["account.account"].search_count(
            [
                ("account_type", "=", "equity_unaffected"),
                ("company_ids", "=", self.company_id.id),
            ]
        )
        self.not_only_one_unaffected_earnings_account = count != 1
        # if (
        #     self.company_id
        #     and self.date_range_id.company_id
        #     and self.date_range_id.company_id != self.company_id
        # ):
        #     self.date_range_id = False
        if self.company_id and self.account_journal_ids:
            self.account_journal_ids = self.account_journal_ids.filtered(
                lambda p: p.company_id == self.company_id or not p.company_id
            )
        if self.company_id and self.partner_ids:
            self.partner_ids = self.partner_ids.filtered(
                lambda p: p.company_id == self.company_id or not p.company_id
            )
        if self.company_id and self.account_ids:
            if self.receivable_accounts_only or self.payable_accounts_only:
                self.onchange_type_accounts_only()
            else:
                self.account_ids = self.account_ids.filtered(
                    lambda a: a.company_ids == self.company_id
                )
        if self.company_id and self.cost_center_ids:
            self.cost_center_ids = self.cost_center_ids.filtered(
                lambda c: c.company_id == self.company_id
            )
        res = {
            "domain": {
                "account_ids": [],
                "partner_ids": [],
                "account_journal_ids": [],
                "cost_center_ids": [],
                # "date_range_id": [],
            }
        }
        if not self.company_id:
            return res
        else:
            res["domain"]["account_ids"] += [("company_ids", "=", self.company_id.id)]
            res["domain"]["account_journal_ids"] += [
                ("company_ids", "=", self.company_id.id)
            ]
            res["domain"]["partner_ids"] += self._get_partner_ids_domain()
            res["domain"]["cost_center_ids"] += [
                ("company_id", "=", self.company_id.id)
            ]
            # res["domain"]["date_range_id"] += [
            #     "|",
            #     ("company_id", "=", self.company_id.id),
            #     ("company_id", "=", False),
            # ]
        return res

    # @api.onchange("date_range_id")
    # def onchange_date_range_id(self):
    #     """Handle date range change."""
    #     if self.date_range_id:
    #         self.date_from = self.date_range_id.date_start
    #         self.date_to = self.date_range_id.date_end

    # @api.constrains("company_id", "date_range_id")
    # def _check_company_id_date_range_id(self):
    #     for rec in self.sudo():
    #         if (
    #             rec.company_id
    #             and rec.date_range_id.company_id
    #             and rec.company_id != rec.date_range_id.company_id
    #         ):
    #             raise ValidationError(
    #                 _(
    #                     "The Company in the General Ledger Report Wizard and in "
    #                     "Date Range must be the same."
    #                 )
    #             )

    @api.onchange("receivable_accounts_only", "payable_accounts_only")
    def onchange_type_accounts_only(self):
        """Handle receivable/payable accounts only change."""
        if self.receivable_accounts_only or self.payable_accounts_only:
            domain = [("company_ids", "=", self.company_id.id)]
            if self.receivable_accounts_only and self.payable_accounts_only:
                domain += [
                    ("account_type", "in", ("asset_receivable", "liability_payable"))
                ]
            elif self.receivable_accounts_only:
                domain += [("account_type", "=", "asset_receivable")]
            elif self.payable_accounts_only:
                domain += [("account_type", "=", "liability_payable")]
            self.account_ids = self.env["account.account"].search(domain)
        else:
            self.account_ids = None

    @api.onchange("partner_ids")
    def onchange_partner_ids(self):
        """Handle partners change."""
        if self.partner_ids:
            self.receivable_accounts_only = self.payable_accounts_only = True
        else:
            self.receivable_accounts_only = self.payable_accounts_only = False

    @api.depends("company_id")
    def _compute_unaffected_earnings_account(self):
        for record in self:
            record.unaffected_earnings_account = self.env["account.account"].search(
                [
                    ("account_type", "=", "equity_unaffected"),
                    ("company_ids", "=", record.company_id.id),
                ]
            )

    unaffected_earnings_account = fields.Many2one(
        comodel_name="account.account",
        compute="_compute_unaffected_earnings_account",
        store=True,
    )

    # def _print_report(self, report_type):
    #     self.ensure_one()
    #     data = self._prepare_report_general_ledger()
    #     report_name = "act_revise.general_ledger"
    #     return (
    #         self.env["ir.actions.report"]
    #         .search(
    #             [("report_name", "=", report_name), ("report_type", "=", report_type)],
    #             limit=1,
    #         )
    #         .report_action(self, data=data)
    #     )
    def _print_report(self, report_type):
        self.ensure_one()
        data = self._prepare_report_general_ledger()
        report = self.env["ir.actions.report"].search(
            [("report_name", "=", "l10n_ru_act_rev.general_ledger"), ("report_type", "=", report_type)], limit=1, )

        if self.partner_ids[0].parent_id:
            partner = int(self.partner_ids[0].parent_id.id)
        else:
            partner = int(self.partner_ids[0].id)
        account_data = self.env['account.move.line'].sudo().search([
            ('partner_id', '=', partner),
            ('account_id.account_type', 'in', ('liability_payable', 'asset_receivable')),
            ('account_id.non_trade', '=', False),
            ('date', '<=', self.date_to),
            ('date', '>=', self.date_from)
        ])
        if self.target_move == 'posted' and not account_data.filtered(lambda p: p.parent_state == 'posted') or not account_data:
            raise UserError(f'Проводок для формирования акта по введенным условиям не найдено.')
        return {
            'type': 'ir.actions.act_url',
            'url': '/my/act_revise_contact/%s?date_to=%s&date_from=%s&target_move=%s&company=%s&partner=%s' % (
                urllib.parse.quote(self.get_report_filename()), self.date_to, self.date_from, self.target_move,
                self.company_id.id, partner),
            'target': 'new',
        }

    def _prepare_report_general_ledger(self):
        self.ensure_one()
        return {
            "wizard_id": self.id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "only_posted_moves": self.target_move == "posted",
            "hide_account_at_0": self.hide_account_at_0,
            "foreign_currency": self.foreign_currency,
            "company_id": self.company_id.id,
            "account_ids": self.account_ids.ids,
            "partner_ids": self.partner_ids.ids,
            "grouped_by": self.grouped_by,
            "cost_center_ids": self.cost_center_ids.ids,
            "show_cost_center": self.show_cost_center,
            "journal_ids": self.account_journal_ids.ids,
            "centralize": self.centralize,
            "fy_start_date": self.fy_start_date,
            "unaffected_earnings_account": self.unaffected_earnings_account.id,
            "account_financial_report_lang": self.env.lang,
            "domain": self._get_account_move_lines_domain(),
        }

    def _export(self, report_type):
        """Default export is PDF."""
        return self._print_report(report_type)

    def _get_atr_from_dict(self, obj_id, data, key):
        try:
            return data[obj_id][key]
        except KeyError:
            return data[str(obj_id)][key]

    def numer(self, name):
        if name:
            numeration = re.findall('\d+$', name)
            if numeration: return numeration[0]
        return name

    def get_data_format(self, date):
        if date and date != 'False':
            return dt.ru_strftime(u'%d.%m.%Y г.', date=datetime.strptime(str(date), "%Y-%m-%d"), inflected=True)
        return ''

    def initials(self, fio):
        if fio:
            return (fio.split()[0] + ' ' + ''.join([fio[0:1] + '.' for fio in fio.split()[1:]])).strip()
        return ''

    def rubles(self, sum):
        "Transform sum number in rubles to text"
        text_rubles = numeral.rubles(int(sum))
        copeck = round((sum - int(sum)) * 100)
        text_copeck = numeral.choose_plural(int(copeck), (u"копейка", u"копейки", u"копеек"))
        return ("%s %02d %s") % (text_rubles, copeck, text_copeck)

    def img(self, img, type='png', width=0, height=0):
        if width:
            width = "width='%spx'" % (width)
        else:
            width = " "
        if height:
            height = "height='%spx'" % (height)
        else:
            height = " "
        toreturn = "<img %s %s src='data:image/%s;base64,%s' />" % (
            width,
            height,
            type,
            str(pycompat.to_text(img)))
        return toreturn

    def get_contract(self):
        partner = int(self.partner_ids[0].id)
        contract = self.env['partner.contract.customer'].search(
            [('partner_id', '=', partner), ('state', '=', 'signed')], limit=1)
        if contract:
            return contract

    def get_function_partner(self, partner):
        director = self.env['res.partner'].search([('parent_id', '=', partner), ('type', '=', 'director')], limit=1)
        if director:
            if director.function:
                return director.function or 'отсутствует'

    def get_name_partner(self, partner):
        director = self.env['res.partner'].search([('parent_id', '=', partner), ('type', '=', 'director')], limit=1)
        if director:
            return director.name or 'отсутствует'

    def get_report_filename(self):
        today = date.today()
        d1 = today.strftime("%d-%m-%Y")
        if self.partner_ids[0].parent_id:
            p = ''.join(self.partner_ids[0].parent_id.name)
        else:
            p = ''.join(self.partner_ids[0].name)
        # return 'Акт Сверки '+ d1 + ' ' + self.company_id.name+'_'+p
        return str(self.company_id.id) + ' - '  + ' ' + d1

    def sorted_lines(self, list):
        list = sorted(list, key=lambda k: k.get('date'), reverse=False)
        return list











































#
# import time
# from ast import literal_eval
# from odoo import _, api, fields, models
# from odoo.tools import date_utils,pycompat
# from pytils import dt,numeral
# from datetime import datetime, date
# import re
# import urllib
#
# class GeneralLedgerReportWizard(models.TransientModel):
#     """General ledger report wizard."""
#
#     _name = "general.ledger.act_revise.wizard"
#     _description = "General Ledger Report Wizard"
#     _inherit = "act_revise.abstract_wizard"
#
#     # date_range_id = fields.Many2one(comodel_name="date.range", string="Date range")
#     date_from = fields.Date(string="РќР°С‡Р°Р»Рѕ РґР°С‚С‹", required=True, default=lambda self: self._init_date_from())
#     date_to = fields.Date(string="РљРѕРЅРµС† РґР°С‚С‹", required=True, default=fields.Date.context_today)
#     fy_start_date = fields.Date(compute="_compute_fy_start_date")
#     target_move = fields.Selection(
#         [("posted", "Р’СЃРµ РїСЂРѕРІРµРґРµРЅРЅС‹Рµ РїСЂРѕРІРѕРґРєРё"), ("all", "Р’СЃРµ РїСЂРѕРІРѕРґРєРё")],
#         string="Р¦РµР»СЊ РѕРїРµСЂР°С†РёРё",
#         required=True,
#         default="posted",
#     )
#     account_ids = fields.Many2many(
#         comodel_name="account.account", string=_("Filter accounts")
#     )
#     centralize = fields.Boolean(string=_("Activate centralization"), default=True)
#     hide_account_at_0 = fields.Boolean(
#         string=_("Hide account ending balance at 0"),
#         help=_("Use this filter to hide an account or a partner "
#         "with an ending balance at 0. "
#         "If partners are filtered, "
#         "debits and credits totals will not match the trial balance."),
#     )
#     receivable_accounts_only = fields.Boolean()
#     payable_accounts_only = fields.Boolean()
#     partner_ids = fields.Many2many(
#         comodel_name="res.partner",
#         string=_("Filter partners"),
#         default=lambda self: self._default_partners(),
#     )
#     account_journal_ids = fields.Many2many(
#         comodel_name="account.journal", string=_("Filter journals")
#     )
#     cost_center_ids = fields.Many2many(
#         comodel_name="account.analytic.account", string=_("Filter cost centers")
#     )
#
#     not_only_one_unaffected_earnings_account = fields.Boolean(readonly=True)
#     foreign_currency = fields.Boolean(
#         string=_("Show foreign currency"),
#         help=_("Display foreign currency for move lines, unless "
#         "account currency is not setup through chart of accounts "
#         "will display initial and final balance in that currency."),
#         default=lambda self: self._default_foreign_currency(),
#     )
#     account_code_from = fields.Many2one(
#         comodel_name="account.account",
#         help="Starting account in a range",
#     )
#     account_code_to = fields.Many2one(
#         comodel_name="account.account",
#         help="Ending account in a range",
#     )
#     grouped_by = fields.Selection(
#         selection=[("", "None"), ("partners", "Partners"), ("taxes", "Taxes")],
#         default="partners",
#     )
#     show_cost_center = fields.Boolean(
#         string="Show Analytic Account",
#         default=True,
#     )
#     domain = fields.Char(
#         string="Journal Items Domain",
#         default=[],
#         help="This domain will be used to select specific domain for Journal " "Items",
#     )
#
#     # def _print_report(self, report_type):
#     #     self.ensure_one()
#     #     data = self._prepare_report_general_ledger()
#     #     report = self.env["ir.actions.report"].search(
#     #         [("report_name", "=", "act_revise.general_ledger"), ("report_type", "=", report_type)], limit=1, )
#     #     if self.partner_ids[0].parent_id:
#     #         partner = int(self.partner_ids[0].parent_id.id)
#     #     else:
#     #         partner = int(self.partner_ids[0].id)
#     #     return {
#     #         'type': 'ir.actions.act_url',
#     #         'url': '/my/act_revise_contact/%s?date_to=%s&date_from=%s&target_move=%s&company=%s&partner=%s' % (
#     #             urllib.parse.quote(self.get_report_filename()), self.date_to, self.date_from, self.target_move,
#     #             self.company_id.id, partner),
#     #         'target': 'new',
#     #     }
#
#     def _get_account_move_lines_domain(self):
#         domain = literal_eval(self.domain) if self.domain else []
#         return domain
#
#     @api.onchange("account_code_from", "account_code_to")
#     def on_change_account_range(self):
#         if (
#             self.account_code_from
#             and self.account_code_from.code.isdigit()
#             and self.account_code_to
#             and self.account_code_to.code.isdigit()
#         ):
#             start_range = self.account_code_from.code
#             end_range = self.account_code_to.code
#             self.account_ids = self.env["account.account"].search(
#                 [("code", ">=", start_range), ("code", "<=", end_range)]
#             )
#             if self.company_id:
#                 self.account_ids = self.account_ids.filtered(
#                     lambda a: a.company_id == self.company_id
#                 )
#
#     def _init_date_from(self):
#         """set start date to begin of current year if fiscal year running"""
#         today = fields.Date.context_today(self)
#         company = self.company_id or self.env.company
#         last_fsc_month = company.fiscalyear_last_month
#         last_fsc_day = company.fiscalyear_last_day
#
#         if (
#             today.month < int(last_fsc_month)
#             or today.month == int(last_fsc_month)
#             and today.day <= last_fsc_day
#         ):
#             return time.strftime("%Y-01-01")
#         else:
#             return False
#
#     def _default_foreign_currency(self):
#         return self.env.user.has_group("base.group_multi_currency")
#
#     @api.depends("date_from")
#     def _compute_fy_start_date(self):
#         for wiz in self:
#             if wiz.date_from:
#                 date_from, date_to = date_utils.get_fiscal_year(
#                     wiz.date_from,
#                     day=self.company_id.fiscalyear_last_day,
#                     month=int(self.company_id.fiscalyear_last_month),
#                 )
#                 wiz.fy_start_date = date_from
#             else:
#                 wiz.fy_start_date = False
#
#     @api.onchange("company_id")
#     def onchange_company_id(self):
#         """Handle company change."""
#         count = self.env["account.account"].search_count(
#             [
#                 ("account_type", "=", "equity_unaffected"),
#                 ("company_id", "=", self.company_id.id),
#             ]
#         )
#         self.not_only_one_unaffected_earnings_account = count != 1
#         # if (
#         #     self.company_id
#         #     and self.date_range_id.company_id
#         #     and self.date_range_id.company_id != self.company_id
#         # ):
#         #     self.date_range_id = False
#         if self.company_id and self.account_journal_ids:
#             self.account_journal_ids = self.account_journal_ids.filtered(
#                 lambda p: p.company_id == self.company_id or not p.company_id
#             )
#         if self.company_id and self.partner_ids:
#             self.partner_ids = self.partner_ids.filtered(
#                 lambda p: p.company_id == self.company_id or not p.company_id
#             )
#         if self.company_id and self.account_ids:
#             if self.receivable_accounts_only or self.payable_accounts_only:
#                 self.onchange_type_accounts_only()
#             else:
#                 self.account_ids = self.account_ids.filtered(
#                     lambda a: a.company_id == self.company_id
#                 )
#         if self.company_id and self.cost_center_ids:
#             self.cost_center_ids = self.cost_center_ids.filtered(
#                 lambda c: c.company_id == self.company_id
#             )
#         res = {
#             "domain": {
#                 "account_ids": [],
#                 "partner_ids": [],
#                 "account_journal_ids": [],
#                 "cost_center_ids": [],
#                 # "date_range_id": [],
#             }
#         }
#         if not self.company_id:
#             return res
#         else:
#             res["domain"]["account_ids"] += [("company_id", "=", self.company_id.id)]
#             res["domain"]["account_journal_ids"] += [
#                 ("company_id", "=", self.company_id.id)
#             ]
#             res["domain"]["partner_ids"] += self._get_partner_ids_domain()
#             res["domain"]["cost_center_ids"] += [
#                 ("company_id", "=", self.company_id.id)
#             ]
#             # res["domain"]["date_range_id"] += [
#             #     "|",
#             #     ("company_id", "=", self.company_id.id),
#             #     ("company_id", "=", False),
#             # ]
#         return res
#
#     # @api.onchange("date_range_id")
#     # def onchange_date_range_id(self):
#     #     """Handle date range change."""
#     #     if self.date_range_id:
#     #         self.date_from = self.date_range_id.date_start
#     #         self.date_to = self.date_range_id.date_end
#
#     # @api.constrains("company_id", "date_range_id")
#     # def _check_company_id_date_range_id(self):
#     #     for rec in self.sudo():
#     #         if (
#     #             rec.company_id
#     #             and rec.date_range_id.company_id
#     #             and rec.company_id != rec.date_range_id.company_id
#     #         ):
#     #             raise ValidationError(
#     #                 _(
#     #                     "The Company in the General Ledger Report Wizard and in "
#     #                     "Date Range must be the same."
#     #                 )
#     #             )
#
#     @api.onchange("receivable_accounts_only", "payable_accounts_only")
#     def onchange_type_accounts_only(self):
#         """Handle receivable/payable accounts only change."""
#         if self.receivable_accounts_only or self.payable_accounts_only:
#             domain = [("company_id", "=", self.company_id.id)]
#             if self.receivable_accounts_only and self.payable_accounts_only:
#                 domain += [
#                     ("account_type", "in", ("asset_receivable", "liability_payable"))
#                 ]
#             elif self.receivable_accounts_only:
#                 domain += [("account_type", "=", "asset_receivable")]
#             elif self.payable_accounts_only:
#                 domain += [("account_type", "=", "liability_payable")]
#             self.account_ids = self.env["account.account"].search(domain)
#         else:
#             self.account_ids = None
#
#     @api.onchange("partner_ids")
#     def onchange_partner_ids(self):
#         """Handle partners change."""
#         if self.partner_ids:
#             self.receivable_accounts_only = self.payable_accounts_only = True
#         else:
#             self.receivable_accounts_only = self.payable_accounts_only = False
#
#     @api.depends("company_id")
#     def _compute_unaffected_earnings_account(self):
#         for record in self:
#             record.unaffected_earnings_account = self.env["account.account"].search(
#                 [
#                     ("account_type", "=", "equity_unaffected"),
#                     ("company_id", "=", record.company_id.id),
#                 ]
#             )
#
#     unaffected_earnings_account = fields.Many2one(
#         comodel_name="account.account",
#         compute="_compute_unaffected_earnings_account",
#         store=True,
#     )
#
#     # def _print_report(self, report_type):
#     #     self.ensure_one()
#     #     data = self._prepare_report_general_ledger()
#     #     report_name = "act_revise.general_ledger"
#     #     return (
#     #         self.env["ir.actions.report"]
#     #         .search(
#     #             [("report_name", "=", report_name), ("report_type", "=", report_type)],
#     #             limit=1,
#     #         )
#     #         .report_action(self, data=data)
#     #     )
#     def _print_report(self, report_type):
#         self.ensure_one()
#         data = self._prepare_report_general_ledger()
#         report = self.env["ir.actions.report"].search(
#             [("report_name", "=", "act_revise.general_ledger"), ("report_type", "=", report_type)], limit=1, )
#         # report.report_name='Test'
#         # report.headers.add('Content-Disposition', 'attachment; filename="Test.pdf";')
#         # pdf, _ = request.env.ref('act_revise.action_print_report_general_ledger_qweb').sudo().render_qweb_pdf(self,data=data)
#         # pdfhttpheaders = [('Content-Type', 'application/pdf'), ('Content-Length', len(pdf)),('Content-Disposition', 'attachment; filename="%s";' % report_name),]
#         # return request.make_response(pdf, headers=pdfhttpheaders)
#         # return (
#         # self.env["ir.actions.report"]
#         # .search(
#         #    [("report_name", "=", "act_revise.general_ledger"), ("report_type", "=", report_type)],
#         #    limit=1,
#         # )
#         #   report.report_action(self, data=data)
#         # )
#         # name='Test'
#         if self.partner_ids[0].parent_id:
#             partner = int(self.partner_ids[0].parent_id.id)
#         else:
#             partner = int(self.partner_ids[0].id)
#         account_data = self.env['account.move.line'].sudo().search([
#             ('partner_id', '=', partner.id),
#             ('account_id.account_type', 'in', ('liability_payable', 'asset_receivable')),
#             ('account_id.non_trade', '=', False),
#             ('date', '<=', self.date_to),
#             ('date', '>=', self.date_from)
#         ])
#         if not account_data:
#             raise UserError(f'Проводок для формирования акта по введенным условиям не найдено.')
#         return {
#             'type': 'ir.actions.act_url',
#             'url': '/my/act_revise_contact/%s?date_to=%s&date_from=%s&target_move=%s&company=%s&partner=%s' % (
#                 urllib.parse.quote(self.get_report_filename()), self.date_to, self.date_from, self.target_move,
#                 self.company_id.id, partner),
#             'target': 'new',
#         }
#
#     def _prepare_report_general_ledger(self):
#         self.ensure_one()
#         return {
#             "wizard_id": self.id,
#             "date_from": self.date_from,
#             "date_to": self.date_to,
#             "only_posted_moves": self.target_move == "posted",
#             "hide_account_at_0": self.hide_account_at_0,
#             "foreign_currency": self.foreign_currency,
#             "company_id": self.company_id.id,
#             "account_ids": self.account_ids.ids,
#             "partner_ids": self.partner_ids.ids,
#             "grouped_by": self.grouped_by,
#             "cost_center_ids": self.cost_center_ids.ids,
#             "show_cost_center": self.show_cost_center,
#             "journal_ids": self.account_journal_ids.ids,
#             "centralize": self.centralize,
#             "fy_start_date": self.fy_start_date,
#             "unaffected_earnings_account": self.unaffected_earnings_account.id,
#             "account_financial_report_lang": self.env.lang,
#             "domain": self._get_account_move_lines_domain(),
#         }
#
#     def _export(self, report_type):
#         """Default export is PDF."""
#         return self._print_report(report_type)
#
#     def _get_atr_from_dict(self, obj_id, data, key):
#         try:
#             return data[obj_id][key]
#         except KeyError:
#             return data[str(obj_id)][key]
#
#     def numer(self, name):
#         if name:
#             numeration = re.findall('\d+$', name)
#             if numeration: return numeration[0]
#         return name
#
#     def get_data_format(self, date):
#         if date and date != 'False':
#             return dt.ru_strftime(u'%d.%m.%Y Рі.', date=datetime.strptime(str(date), "%Y-%m-%d"), inflected=True)
#         return ''
#
#     def initials(self, fio):
#         if fio:
#             return (fio.split()[0] + ' ' + ''.join([fio[0:1] + '.' for fio in fio.split()[1:]])).strip()
#         return ''
#
#     def rubles(self, sum):
#         "Transform sum number in rubles to text"
#         text_rubles = numeral.rubles(int(sum))
#         copeck = round((sum - int(sum)) * 100)
#         text_copeck = numeral.choose_plural(int(copeck), (u"РєРѕРїРµР№РєР°", u"РєРѕРїРµР№РєРё", u"РєРѕРїРµРµРє"))
#         return ("%s %02d %s") % (text_rubles, copeck, text_copeck)
#
#     def img(self, img, type='png', width=0, height=0):
#         if width:
#             width = "width='%spx'" % (width)
#         else:
#             width = " "
#         if height:
#             height = "height='%spx'" % (height)
#         else:
#             height = " "
#         toreturn = "<img %s %s src='data:image/%s;base64,%s' />" % (
#             width,
#             height,
#             type,
#             str(pycompat.to_text(img)))
#         return toreturn
#
#     def get_contract(self):
#         partner = int(self.partner_ids[0].id)
#         contract = self.env['partner.contract.customer'].search(
#             [('partner_id', '=', partner), ('state', '=', 'signed')], limit=1)
#         if contract:
#             return contract
#
#     def get_function_partner(self, partner):
#         director = self.env['res.partner'].search([('parent_id', '=', partner), ('type', '=', 'director')], limit=1)
#         if director:
#             if director.function:
#                 return director.function or 'РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚'
#
#     def get_name_partner(self, partner):
#         director = self.env['res.partner'].search([('parent_id', '=', partner), ('type', '=', 'director')], limit=1)
#         if director:
#             return director.name or 'РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚'
#
#     def get_report_filename(self):
#         today = date.today()
#         d1 = today.strftime("%d-%m-%Y")
#         if self.partner_ids[0].parent_id:
#             p = ''.join(self.partner_ids[0].parent_id.name)
#         else:
#             p = ''.join(self.partner_ids[0].name)
#         # return 'РђРєС‚ РЎРІРµСЂРєРё '+ d1 + ' ' + self.company_id.name+'_'+p
#         return str(self.company_id.id) + ' - '  + ' ' + d1
#
#     def sorted_lines(self, list):
#         list = sorted(list, key=lambda k: k.get('date'), reverse=False)
#         return list
