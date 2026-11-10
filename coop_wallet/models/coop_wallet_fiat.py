# -*- coding: utf-8 -*-
"""Данные вкладки «Фиат» с переключателем валют (задача 400).

Всё здесь — вычисляемое и не хранится: экран собирается из остатков по
валютам (`coop_balances`), сводки «Все» в валюте страны участника и
счетов. Выбор валюты — строка «all» или код; между сеансами он не
сохраняется, на входе всегда «Все».
"""
import json
from datetime import date

from markupsafe import Markup, escape

from odoo import _, api, fields, models

ALL = 'all'
# У евро и доллара нет одной страны — в списке вместо неё название.
NO_COUNTRY_LABEL = {'EUR': 'Евро', 'USD': 'Доллар США'}


def fmt_amount(amount, currency, signed=False):
    """«1 234,56 ₽»: пробел-тысячи, запятая, код после числа (рубль — знаком)."""
    text = '{:,.2f}'.format(abs(amount)).replace(',', ' ').replace('.', ',')
    sign = '−' if amount < 0 else ('+' if signed and amount > 0 else '')
    unit = '₽' if currency.name == 'RUB' else currency.name
    return '%s%s %s' % (sign, text, unit)


class CoopWalletFiat(models.Model):
    _inherit = 'coop.wallet'

    # Не хранится: на входе всегда «Все», выбор живёт только в открытой форме.
    fiat_currency = fields.Char(
        string='Валюта вкладки', compute='_compute_fiat_currency',
        readonly=False, store=False,
        help='«all» — все валюты в пересчёте, иначе код одной валюты.')
    fiat_currency_items = fields.Char(
        compute='_compute_fiat_view', string='Валюты переключателя')
    fiat_is_all = fields.Boolean(compute='_compute_fiat_view')
    fiat_stat_total = fields.Char(compute='_compute_fiat_view')
    fiat_stat_free = fields.Char(compute='_compute_fiat_view')
    fiat_stat_count = fields.Integer(compute='_compute_fiat_view')
    fiat_stat_caption = fields.Char(compute='_compute_fiat_view')
    fiat_rates_note = fields.Html(compute='_compute_fiat_view', sanitize=False)
    fiat_by_currency = fields.Html(compute='_compute_fiat_view', sanitize=False)
    fiat_account_ids = fields.Many2many(
        'coop.wallet.account', compute='_compute_fiat_view',
        string='Мои счета')
    fiat_movement_ids = fields.Many2many(
        'coop.wallet.movement', compute='_compute_fiat_view',
        string='История операций')
    fiat_can_pay = fields.Boolean(compute='_compute_fiat_view')
    fiat_pay_hint = fields.Char(compute='_compute_fiat_view')
    fiat_account_hint = fields.Char(compute='_compute_fiat_view')

    def _compute_fiat_currency(self):
        for wallet in self:
            wallet.fiat_currency = ALL

    # ── Сборка экрана ────────────────────────────────────────────────────

    def _fiat_label(self, currency):
        return (currency.coop_country_id.name
                or NO_COUNTRY_LABEL.get(currency.name) or currency.name)

    def _fiat_available(self, row):
        """Доступно к выводу: рубли — за вычетом обещанного по графикам,
        остальные валюты обещаний не имеют."""
        if row['currency'] == self.currency_id:
            return self.fiat_available
        return row['balance']

    @api.depends('fiat_currency', 'movement_ids.amount', 'movement_ids.state',
                 'movement_ids.currency_id', 'account_ids.currency_id',
                 'account_ids.kind', 'partner_id.coop_summary_country_id',
                 'partner_id.coop_citizenship_ids', 'fiat_available')
    def _compute_fiat_view(self):
        Currency = self.env['res.currency'].sudo().with_context(active_test=False)
        enabled = Currency.search([('coop_wallet_enabled', '=', True)])
        today = date.today()
        for wallet in self:
            rows = wallet.coop_balances()
            present = {row['currency'] for row in rows}
            choice = wallet.fiat_currency or ALL
            known = {c.name for c in enabled}
            if choice != ALL and choice not in known:
                choice = ALL
            wallet.fiat_is_all = choice == ALL

            ordered = sorted(enabled, key=lambda c: (c.name != 'RUB', c.name))
            wallet.fiat_currency_items = json.dumps([
                {'code': c.name, 'country': wallet._fiat_label(c),
                 'shown': c in present} for c in ordered], ensure_ascii=False)

            target = wallet.partner_id.coop_summary_currency()
            if choice == ALL:
                summary = wallet.coop_summary(target, today)
                missing = summary['missing']
                if missing:
                    wallet.fiat_stat_total = '—'
                    wallet.fiat_stat_free = '—'
                    wallet.fiat_stat_caption = _('курс не получен')
                else:
                    wallet.fiat_stat_total = '≈ ' + fmt_amount(
                        summary['total'], target)
                    free = 0.0
                    for row in rows:
                        value = self.env['coop.currency.rate'].coop_convert(
                            wallet._fiat_available(row), row['currency'],
                            target, today)
                        free += value or 0.0
                    wallet.fiat_stat_free = '≈ ' + fmt_amount(free, target)
                    wallet.fiat_stat_caption = _('по курсу ЦБ РФ на дату')
                wallet.fiat_stat_count = summary['count']
                wallet.fiat_rates_note = wallet._fiat_rates_note(
                    missing, summary['stale'])
                wallet.fiat_by_currency = wallet._fiat_by_currency_html(
                    rows, target, today)
                accounts = wallet.account_ids
                movements = wallet.movement_ids
            else:
                currency = enabled.filtered(lambda c: c.name == choice)[:1]
                row = next((r for r in rows if r['currency'] == currency), None) \
                    or {'currency': currency, 'balance': 0.0, 'count': 0}
                wallet.fiat_stat_total = fmt_amount(row['balance'], currency)
                wallet.fiat_stat_free = fmt_amount(
                    wallet._fiat_available(row), currency)
                wallet.fiat_stat_count = row['count']
                wallet.fiat_stat_caption = False
                wallet.fiat_rates_note = False
                wallet.fiat_by_currency = False
                accounts = wallet.account_ids.filtered(
                    lambda a: a.currency_id == currency)
                movements = wallet.movement_ids.filtered(
                    lambda m: m.currency_id == currency)
            wallet.fiat_account_ids = accounts
            wallet.fiat_movement_ids = movements

            digital = wallet.account_ids.filtered(
                lambda a: a.kind == 'cbdc' and a.currency_id.name == 'RUB')
            wallet.fiat_can_pay = choice == 'RUB' and bool(digital)
            if wallet.fiat_can_pay:
                wallet.fiat_pay_hint = False
            elif choice == 'RUB':
                wallet.fiat_pay_hint = _(
                    'Пополнить и вывести можно через цифровой рубль: '
                    'сначала добавьте счёт «Цифровой рубль».')
            else:
                wallet.fiat_pay_hint = _(
                    'Пополнить и вывести можно через цифровой рубль: '
                    'выберите валюту RUB.')
            if not wallet.account_ids:
                wallet.fiat_account_hint = _('Счетов пока нет.')
            elif choice != ALL and not accounts:
                wallet.fiat_account_hint = _(
                    'Счетов в валюте %s нет.', choice)
            else:
                wallet.fiat_account_hint = False

    def _fiat_rates_note(self, missing, stale):
        parts = []
        if missing:
            parts.append(escape(_(
                'Курсы не получены (%s). Остатки показаны по валютам, без '
                'общего итога.', ', '.join(c.name for c in missing))))
        if stale:
            parts.append(escape(_(
                'Курс устарел (%s): ЦБ не публиковал его больше трёх дней.',
                ', '.join(c.name for c in stale))))
        if not parts:
            return False
        return Markup('<div class="o_coop_note o_coop_note_warn">%s</div>') % (
            Markup(' ').join(parts))

    def _fiat_by_currency_html(self, rows, target, today):
        Rate = self.env['coop.currency.rate']
        if not rows:
            return False
        body = []
        for row in rows:
            currency = row['currency']
            accounts = len(self.account_ids.filtered(
                lambda a, c=currency: a.currency_id == c))
            converted = Rate.coop_convert(row['balance'], currency, target, today)
            inside = ('—' if converted is None
                      else '≈ ' + fmt_amount(converted, target))
            body.append(Markup(
                '<tr><td class="o_coop_cur_code">%s</td><td class="o_coop_cur_num">%s</td>'
                '<td class="o_coop_cur_num">%s</td><td class="o_coop_cur_num">%s</td>'
                '<td class="o_coop_cur_num">%s</td></tr>') % (
                currency.name, fmt_amount(row['balance'], currency),
                fmt_amount(self._fiat_available(row), currency), accounts,
                inside))
        head = Markup(
            '<thead><tr><th>Валюта</th><th class="o_coop_cur_num">Остаток</th>'
            '<th class="o_coop_cur_num">Доступно к выводу</th>'
            '<th class="o_coop_cur_num">Счетов</th>'
            '<th class="o_coop_cur_num">В %s</th></tr></thead>') % target.name
        return Markup(
            '<div class="o_coop_cur_wrap"><table class="o_coop_cur_table">%s'
            '<tbody>%s</tbody></table></div>') % (head, Markup('').join(body))

    # ── Действия ─────────────────────────────────────────────────────────

    def action_add_account(self):
        """Окно «Добавить счёт»: валюта — выбранная, страна — из гражданства."""
        self.ensure_one()
        context = {'default_wallet_id': self.id}
        currency = self.env['res.currency'].sudo().with_context(
            active_test=False).search([('name', '=', self.fiat_currency)], limit=1)
        if currency:
            context['default_currency_id'] = currency.id
        country = self.partner_id.coop_citizenship_ids[:1]
        if country:
            context['default_country_id'] = country.id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Добавить счёт'),
            'res_model': 'coop.wallet.account',
            'view_mode': 'form',
            'target': 'new',
            'context': context,
        }
