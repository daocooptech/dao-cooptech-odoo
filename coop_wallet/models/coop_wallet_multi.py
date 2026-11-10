# -*- coding: utf-8 -*-
"""Несколько валют в фиатном кошельке: остатки, сводка, гражданства (задача 400).

Остатки разных валют не складываются без пересчёта. `coop_balances()` —
остаток по каждой валюте как есть; `coop_summary()` — сводка «Все» в валюте
страны участника по курсу ЦБ на дату, где нет курса — `None`, а не ноль.
"""
from odoo import api, fields, models


class CoopWalletMulti(models.Model):
    _inherit = 'coop.wallet'

    account_ids = fields.One2many(
        'coop.wallet.account', 'wallet_id', string='Счета')

    def coop_balances(self):
        """Остаток и число операций по каждой валюте: список словарей."""
        self.ensure_one()
        by_currency = {}
        for move in self.movement_ids:
            row = by_currency.setdefault(
                move.currency_id, {'currency': move.currency_id,
                                   'balance': 0.0, 'count': 0})
            row['count'] += 1
            if move.state == 'confirmed':
                row['balance'] += move.amount
        # Валюта счёта без движений — тоже строка: счёт есть, остаток ноль.
        for account in self.account_ids:
            by_currency.setdefault(
                account.currency_id, {'currency': account.currency_id,
                                      'balance': 0.0, 'count': 0})
        return sorted(by_currency.values(),
                      key=lambda row: row['currency'].name)

    def coop_summary(self, target=None, on=None):
        """Сводка «Все»: итог в валюте сводки.

        Возвращает {'currency', 'total', 'missing': [валюты без курса],
        'stale': [валюты с устаревшим курсом], 'count'}; `total` — по
        валютам, у которых курс есть.
        """
        self.ensure_one()
        Rate = self.env['coop.currency.rate']
        target = target or self.partner_id.coop_summary_currency()
        total, missing, stale, count = 0.0, [], [], 0
        for row in self.coop_balances():
            count += row['count']
            currency = row['currency']
            if not row['balance']:
                # Пустой остаток не нужно пересчитывать: нет курса — не помеха.
                continue
            converted = Rate.coop_convert(row['balance'], currency, target, on)
            if converted is None:
                missing.append(currency)
                continue
            total += converted
            rate = Rate.coop_rate(currency, on)
            if rate and rate[2]:
                stale.append(currency)
        return {'currency': target, 'total': total, 'missing': missing,
                'stale': stale, 'count': count}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_citizenship_ids = fields.Many2many(
        'res.country', 'coop_partner_citizenship_rel', 'partner_id',
        'country_id', string='Гражданства',
        help='Список в профиле: по нему считаются страна сводки '
             'кошелька и резидентство.')
    coop_ru_residence_permit = fields.Boolean(
        string='ВНЖ или ПМЖ в России',
        help='Со слов участника, без проверки документа.')
    coop_summary_country_id = fields.Many2one(
        'res.country', string='Страна для сводки',
        help='В кошельке на вкладке «Все» суммы пересчитываются в валюту '
             'этой страны. Пусто — первое гражданство, иначе Россия.')

    def coop_summary_currency(self):
        """Валюта сводки кошелька: страна сводки → гражданство → рубль."""
        self.ensure_one()
        wallet_countries = self.env['res.currency'].sudo().with_context(
            active_test=False).search(
            [('coop_wallet_enabled', '=', True)]).mapped('coop_country_id')
        candidates = [self.coop_summary_country_id] + list(
            self.coop_citizenship_ids)
        for country in candidates:
            if country and country in wallet_countries:
                return self.env['res.currency'].sudo().with_context(
                    active_test=False).search([
                        ('coop_wallet_enabled', '=', True),
                        ('coop_country_id', '=', country.id)], limit=1)
        return self.env.ref('base.RUB')

    def coop_is_ru_resident(self):
        """Резидент России со слов: гражданство РФ или ВНЖ.

        Налоговое резидентство (183 дня) платформа не определяет. Модуль
        настроек дополняет: у кого списка гражданств ещё нет — берётся
        прежняя отметка «валютный резидент».
        """
        self.ensure_one()
        ru = self.env.ref('base.ru', raise_if_not_found=False)
        return bool(self.coop_ru_residence_permit
                    or (ru and ru in self.coop_citizenship_ids))

    def coop_currency_warning(self, other, currency):
        """Предупреждение о расчёте валютой между резидентами РФ (решение 640).

        Только текст, расчёт не блокируется: владелец 10.11.2026 выбрал
        «вычислять, только предупреждать». Пусто — предупреждать не о чем.
        """
        self.ensure_one()
        if (currency != self.env.ref('base.RUB')
                and self.coop_is_ru_resident() and other.coop_is_ru_resident()):
            return ('Оба участника — резиденты России: расчёты между '
                    'резидентами, как правило, идут в рублях. Проверьте, '
                    'что расчёт валютой допустим для вашей сделки.')
        return ''

    def coop_foreign_account_hint(self, country):
        """Подсказка резиденту РФ при добавлении иностранного счёта."""
        self.ensure_one()
        ru = self.env.ref('base.ru', raise_if_not_found=False)
        if self.coop_is_ru_resident() and country and ru and country != ru:
            return ('Резидент России уведомляет налоговую об открытии, закрытии '
                    'и смене реквизитов счёта в иностранном банке в течение '
                    'месяца; у физлиц бывают исключения. Платформа за вас '
                    'этого не делает.')
        return ''
