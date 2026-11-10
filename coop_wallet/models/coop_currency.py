# -*- coding: utf-8 -*-
"""Валюты фиатного кошелька и курсы ЦБ РФ (задача 400, решения 639, 640).

Набор — валюты стран БРИКС и СНГ, евро, доллар и партнёры БРИКС. Валюта —
штатная `res.currency`; платформа добавляет к ней страну и признак «есть в
кошельке». Курс — рублей за единицу валюты на дату; рубль курса не имеет
(он единица счёта). Остатки разных валют не складываются без пересчёта:
пересчёт идёт через рубль по курсу ЦБ на дату, и когда курса нет — это
не ноль, а «курс не получен» (`None`).
"""
import logging
import urllib.request
from datetime import datetime, timedelta
from xml.etree import ElementTree

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

CBR_URL = 'https://www.cbr.ru/scripts/XML_daily.asp'
# Курс старше — «устарел»: ЦБ не публикует по выходным, три дня — это
# выходные с запасом на праздник.
STALE_AFTER_DAYS = 3


# Валюты кошелька: код → страна (None — несколько стран). БРИКС, СНГ,
# евро, доллар и партнёры БРИКС. SAR и MDL — не включены до отдельного
# слова владельца (решение 640).
WALLET_CURRENCIES = {
    'BRL': 'br', 'CNY': 'cn', 'EGP': 'eg', 'ETB': 'et', 'INR': 'in',
    'IDR': 'id', 'IRR': 'ir', 'RUB': 'ru', 'ZAR': 'za', 'AED': 'ae',
    'AMD': 'am', 'AZN': 'az', 'BYN': 'by', 'KZT': 'kz', 'KGS': 'kg',
    'TJS': 'tj', 'UZS': 'uz', 'TMT': 'tm',
    'EUR': None, 'USD': None,
    'CUP': 'cu', 'VND': 'vn', 'THB': 'th', 'BOB': 'bo', 'MYR': 'my',
    'UGX': 'ug', 'NGN': 'ng',
}


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    coop_wallet_enabled = fields.Boolean(
        string='Есть в кошельке', index=True,
        help='Валюта доступна для счетов и остатков в фиатном кошельке.')
    coop_country_id = fields.Many2one(
        'res.country', string='Страна валюты',
        help='Страна, чья это валюта. У евро и доллара пусто: их несколько '
             'стран.')
    coop_rate_ids = fields.One2many(
        'coop.currency.rate', 'currency_id', string='Курсы к рублю')

    @api.model
    def coop_enable_wallet_currencies(self):
        """Включить валюты кошелька: активна, со страной, знак рубля «₽».

        Функцией, а не записями XML: валюты принадлежат `base` и помечены
        там «не обновлять», поэтому запись из чужого модуля молча
        пропускалась (замерено 10.11.2026: список включённых был пуст).
        """
        Country = self.env['res.country']
        for code, country_code in WALLET_CURRENCIES.items():
            currency = self.with_context(active_test=False).search(
                [('name', '=', code)], limit=1)
            if not currency:
                continue
            country = Country.search(
                [('code', '=', country_code.upper())], limit=1)                 if country_code else Country
            vals = {'active': True, 'coop_wallet_enabled': True,
                    'coop_country_id': country.id or False}
            if code == 'RUB':
                vals['symbol'] = '₽'
            currency.write(vals)
        return True


class CoopCurrencyRate(models.Model):
    _name = 'coop.currency.rate'
    _description = 'Курс валюты к рублю на дату'
    _order = 'date desc, id desc'
    _rec_name = 'currency_id'

    currency_id = fields.Many2one(
        'res.currency', string='Валюта', required=True, index=True,
        ondelete='cascade')
    date = fields.Date(string='Дата', required=True, index=True)
    rub_per_unit = fields.Float(
        string='Рублей за единицу', digits=(16, 6), required=True)
    source = fields.Selection([
        ('cbr', 'ЦБ РФ'),
        ('manual', 'Вручную'),
    ], string='Источник', default='cbr', required=True)

    _one_per_day = models.Constraint(
        'unique(currency_id, date)', 'На эту дату курс валюты уже есть.')
    _positive = models.Constraint(
        'check(rub_per_unit > 0)', 'Курс должен быть больше нуля.')

    # ── Курс и пересчёт ──────────────────────────────────────────────────

    @api.model
    def _rub(self):
        return self.env.ref('base.RUB')

    @api.model
    def coop_rate(self, currency, on=None):
        """(рублей за единицу, дата курса, устарел) или None, если курса нет."""
        on = on or fields.Date.context_today(self)
        if currency == self._rub():
            return 1.0, on, False
        row = self.sudo().search([
            ('currency_id', '=', currency.id), ('date', '<=', on)], limit=1)
        if not row:
            return None
        stale = (on - row.date) > timedelta(days=STALE_AFTER_DAYS)
        return row.rub_per_unit, row.date, stale

    @api.model
    def coop_convert(self, amount, source, target, on=None):
        """Сумма в другой валюте через рубль; None — курса нет."""
        if source == target:
            return amount
        src = self.coop_rate(source, on)
        dst = self.coop_rate(target, on)
        if not src or not dst:
            return None
        return amount * src[0] / dst[0]

    # ── ЦБ РФ ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_cbr(payload):
        """Разобрать ответ `XML_daily.asp`: (дата, {код: рублей за единицу}).

        Значение в ответе — за `Nominal` единиц и с запятой: «1 000 драм
        за 20,5 ₽» — поэтому делится на номинал.
        """
        root = ElementTree.fromstring(payload)
        day = datetime.strptime(root.get('Date'), '%d.%m.%Y').date()
        rates = {}
        for node in root.findall('Valute'):
            code = (node.findtext('CharCode') or '').strip()
            nominal = float((node.findtext('Nominal') or '1').replace(',', '.'))
            value = float((node.findtext('Value') or '0').replace(',', '.'))
            if code and nominal and value:
                rates[code] = value / nominal
        return day, rates

    @api.model
    def coop_store_rates(self, day, rates):
        """Записать курсы на дату для валют кошелька; вернуть, сколько."""
        currencies = self.env['res.currency'].sudo().with_context(
            active_test=False).search([('coop_wallet_enabled', '=', True)])
        made = 0
        for currency in currencies:
            value = rates.get(currency.name)
            if not value:
                continue
            row = self.sudo().search([
                ('currency_id', '=', currency.id), ('date', '=', day)], limit=1)
            if row:
                row.write({'rub_per_unit': value, 'source': 'cbr'})
            else:
                self.sudo().create({
                    'currency_id': currency.id, 'date': day,
                    'rub_per_unit': value, 'source': 'cbr'})
            made += 1
        return made

    @api.model
    def coop_fetch_cbr_rates(self):
        """Раз в сутки: курсы ЦБ РФ. Сбой — в журнал, а не исключением.

        Падение крона из-за недоступного чужого сервера не должно ничего
        ломать: экран и так покажет «курс не получен» и последний курс с
        пометкой «устарел».
        """
        try:
            request = urllib.request.Request(
                CBR_URL, headers={'User-Agent': 'cooptech-node'})
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read()
            day, rates = self._parse_cbr(payload)
        except Exception as error:  # noqa: BLE001 — любой сбой сети или разбора
            _logger.warning('Курсы ЦБ РФ не получены: %s', error)
            return 0
        made = self.coop_store_rates(day, rates)
        _logger.info('Курсы ЦБ РФ на %s: записано %s', day, made)
        return made
