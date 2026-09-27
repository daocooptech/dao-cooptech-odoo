# -*- coding: utf-8 -*-
"""Резидентство сторон и допустимые способы расчёта для пары (решение 118,
решение 414, п. 1).

Владелец 25.09.2026: «три поля и режим» — валютное резидентство (по
гражданству и ВНЖ), налоговое (по дням), страна — независимо друг от
друга; плюс налоговый режим стороны (он уже есть — `coop_tax_regime`).
По ним — допустимые способы расчёта и их цена для пары сторон.

Правила — из справочника юриста
(`Матчасть/legal-counsel/2026-09-22 — Матрица способов расчёта по
резидентству сторон`, раздел 12): первое сработавшее запрещающее
выигрывает, предупреждающие показываются со сноской, остальное разрешено.
Цена — из справочника способов (`coop.settlement.method.cost_hint`,
разбор бухгалтера). Перечень недружественных государств — данные с датой
и основанием, а не константа в коде.
"""
from odoo import api, fields, models

# Распоряжение Правительства РФ от 05.03.2022 № 430-р (с изменениями).
# Коды ISO; ЕС — все 27 государств-членов. Сверить с актуальной редакцией
# перед юридически значимым использованием (вопрос в базе знаний).
UNFRIENDLY = {
    'AU', 'AL', 'AD', 'GB', 'IS', 'CA', 'LI', 'FM', 'MC', 'NZ', 'NO', 'KR', 'SM',
    'MK', 'SG', 'US', 'TW', 'UA', 'ME', 'CH', 'JP', 'BS',
    # Британские коронные земли и заморские территории, названные в перечне
    # отдельно: Джерси, Ангилья, Британские Виргинские острова, Гибралтар,
    # Гернси, остров Мэн.
    'JE', 'AI', 'VG', 'GI', 'GG', 'IM',
    # Европейский союз
    'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU',
    'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE',
}
UNFRIENDLY_SINCE = '2022-03-05'
UNFRIENDLY_BASIS = 'Распоряжение Правительства РФ от 05.03.2022 № 430-р (с изменениями)'

REGISTRATION_THRESHOLD = 3_000_000  # постановка контракта на учёт, Инструкция ЦБ 181-И
GIFT_LIMIT = 3000                   # п. 1 ст. 575 ГК

# Способы сделки, при которых деньги идут от первой стороны ко второй —
# то же правило, что у графика платежей (coop_deals, `_compute_parties`).
PAYS_FIRST = ('purchase', 'rent', 'job', 'service', 'share', 'credit')


class ResCountry(models.Model):
    _inherit = 'res.country'

    coop_unfriendly = fields.Boolean(
        string='Недружественное государство',
        help='Расчёты с лицами этой страны — в режиме спецсчетов и '
             'разрешений. Перечень меняется; основание и дата — рядом.')
    coop_unfriendly_since = fields.Date(string='В перечне с')
    coop_unfriendly_basis = fields.Char(string='Основание')

    @api.model
    def _coop_mark_unfriendly(self):
        """Отметить перечень при обновлении модуля: записи стран у движка
        помечены «не обновлять», правка файлом данных до них не доходит."""
        countries = self.search([('code', 'in', sorted(UNFRIENDLY))])
        countries.filtered(lambda c: not c.coop_unfriendly).write({
            'coop_unfriendly': True,
            'coop_unfriendly_since': UNFRIENDLY_SINCE,
            'coop_unfriendly_basis': UNFRIENDLY_BASIS,
        })
        return True


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_fx_resident = fields.Boolean(
        string='Валютный резидент РФ', default=True,
        help='По ФЗ-173: гражданин РФ — резидент, где бы ни жил; иностранец — '
             'резидент, если у него вид на жительство в РФ; российская '
             'организация — резидент. От этого зависит, какой валютой можно '
             'платить: между двумя резидентами — только рублями.')
    coop_tax_resident = fields.Boolean(
        string='Налоговый резидент РФ', default=True,
        help='По ст. 207 НК: 183 дня в России за 12 месяцев. Меняется каждый '
             'год и решает ставку и кто удерживает налог. Независим от '
             'валютного: гражданин РФ, живущий в Ереване, — валютный '
             'резидент, но не налоговый.')

    def _coop_kind(self):
        """Вид стороны для правил: частное лицо, коммерческая, кооператив,
        НКО, ДАО."""
        self.ensure_one()
        if not self.is_company:
            return 'person'
        form = self.coop_legal_form_id
        # Группа «децентрализованные» — первой: форма ДАО в справочнике
        # помечена кооперативной, и иначе ДАО получало бы правила
        # кооператива (та же ошибка была в вакансиях, `f6f662a`).
        if form.group_id.code == 'decentralized':
            return 'dao'
        if form.is_cooperative:
            return 'coop'
        return {'commercial': 'commercial',
                'nonprofit': 'nonprofit'}.get(form.group_id.code, 'commercial')


class CoopSettlementMethod(models.Model):
    _inherit = 'coop.settlement.method'

    @api.model
    def _coop_pair(self, payer, payee, context='deal_payment', amount=0.0):
        """Что можно, с чем осторожно и чего нельзя между `payer` и `payee`.

        Возвращает список по способам справочника: вердикт `ok` / `warn` /
        `deny` / `planned`, причины с основаниями, цена и условие."""
        fx_a, fx_b = payer.coop_fx_resident, payee.coop_fx_resident
        cross = fx_a != fx_b
        kind_a, kind_b = payer._coop_kind(), payee._coop_kind()
        unfriendly = [p for p in (payer, payee) if p.country_id.coop_unfriendly]
        out = []
        for method in self.search([]):
            code = method.code
            deny, warn = [], []
            if method.status == 'planned':
                out.append(self._coop_row(method, 'planned', [], []))
                continue
            # ── запрещающие, по убыванию силы ──
            if code == 'share':
                if kind_b != 'coop':
                    deny.append('Пай вносится только в кооператив — п. 1 ст. 123.2 ГК.')
                if context == 'deal_payment':
                    deny.append('Паевой взнос — не способ оплаты сделки: пп. 4 п. 3 ст. 39 НК, п. 2 ст. 170 ГК.')
            if code == 'fx_residents' and not (fx_a and fx_b):
                deny.append('Способ — для двух валютных резидентов; здесь сторона — нерезидент, '
                            'см. «Валюта с нерезидентом».')
            if code == 'fx_residents' and fx_a and fx_b:
                deny.append('Оба — валютные резиденты: платёж только в рублях (ч. 1 ст. 9 ФЗ-173), '
                            'штраф 20–40 % суммы с обеих сторон (ч. 1 ст. 15.25 КоАП).')
            if code == 'fx_cross' and not cross:
                deny.append('Валюта годится только между резидентом и нерезидентом; '
                            'здесь стороны в одном статусе.')
            if code == 'cfa' and context == 'deal_payment' and not cross:
                deny.append('ЦФА внутри страны — не средство платежа (ч. 3 ст. 1 ФЗ-259); '
                            'можно только по внешнеторговому договору с нерезидентом.')
            if code == 'crypto':
                deny.append('Платить цифровой валютой за товары и услуги в России нельзя (282-ФЗ). '
                            'Обмен на бирже — можно, это не оплата.')
            if code == 'tokens' and kind_b != 'dao':
                deny.append('Внутренние токены — не средство оплаты между участниками: без лицензии '
                            'это электронные деньги (п. 18 ст. 3, ч. 1 ст. 12 ФЗ-161).')
            if code == 'gift' and amount > GIFT_LIMIT and kind_a == 'commercial' and kind_b == 'commercial':
                deny.append('Дарение между коммерческими организациями — не больше 3 000 ₽ (п. 1 ст. 575 ГК).')
            # ── требующие основания — со сноской ──
            if cross and amount >= REGISTRATION_THRESHOLD and code in ('rub', 'fx_cross', 'netting', 'cession', 'cfa'):
                warn.append('Контракт с нерезидентом от 3 млн ₽ ставится на учёт в банке (Инструкция ЦБ 181-И).')
            if cross and code in ('netting', 'cession'):
                warn.append('С нерезидентом — проверить репатриацию выручки (ст. 19 ФЗ-173).')
            if cross and code == 'barter':
                warn.append('Внешнеторговый бартер: ст. 44 ФЗ-164, Указ № 1209.')
            if code == 'barter' and kind_b == 'person' and payee.coop_fx_resident and kind_a in ('commercial', 'coop'):
                warn.append('Организация, меняющаяся с частным лицом, выбивает чек (ст. 1.1 ФЗ-54).')
            if code == 'netting' and (payer.coop_tax_regime or '').startswith('usn'):
                warn.append('На УСН доход по зачёту — в день подписания акта (п. 1 ст. 346.17 НК).')
            if unfriendly and not deny:
                names = ', '.join(sorted({p.country_id.name for p in unfriendly}))
                warn.append('Сторона из недружественного государства (%s): режим спецсчетов и '
                            'разрешений.' % names)
            if cross and code == 'cfa' and not deny:
                warn.append('Только через оператора информационной системы — у платформы его пока нет.')
            verdict = 'deny' if deny else ('warn' if warn else 'ok')
            out.append(self._coop_row(method, verdict, deny, warn))
        order = {'ok': 0, 'warn': 1, 'deny': 2, 'planned': 3}
        out.sort(key=lambda r: (order[r['verdict']], r['sequence']))
        return out

    def _coop_row(self, method, verdict, deny, warn):
        return {
            'code': method.code, 'name': method.name, 'sequence': method.sequence,
            'verdict': verdict, 'reasons': deny or warn, 'cost': method.cost_hint or '',
            'condition': method.condition or '',
        }


class CoopDeal(models.Model):
    _inherit = 'coop.deal'

    coop_settlement_html = fields.Html(
        string='Как рассчитаться', compute='_compute_coop_settlement_html', sanitize=False,
        help='Какие способы расчёта законны между этими сторонами — по их '
             'валютному и налоговому резидентству, стране, виду и налоговому '
             'режиму (решения 118, 414).')

    def _coop_payer_payee(self):
        self.ensure_one()
        if self.way in PAYS_FIRST:
            return self.party_a_id, self.party_b_id
        return self.party_b_id, self.party_a_id

    @api.depends('party_a_id', 'party_b_id', 'way', 'amount')
    def _compute_coop_settlement_html(self):
        Method = self.env['coop.settlement.method'].sudo()
        labels = {'ok': 'Можно', 'warn': 'Можно, с оговоркой', 'deny': 'Нельзя',
                  'planned': 'Платформа готовит'}
        for deal in self:
            if not deal.party_a_id or not deal.party_b_id:
                deal.coop_settlement_html = False
                continue
            payer, payee = deal._coop_payer_payee()
            rows = Method._coop_pair(payer.sudo(), payee.sudo(), 'deal_payment', deal.amount or 0.0)

            def who(p):
                bits = ['валютный %s' % ('резидент' if p.coop_fx_resident else 'нерезидент'),
                        'налоговый %s' % ('резидент' if p.coop_tax_resident else 'нерезидент')]
                if p.country_id:
                    bits.append(p.country_id.name)
                regime = dict(p._fields['coop_tax_regime']._description_selection(p.env)).get(p.coop_tax_regime)
                if regime and p.coop_tax_regime != 'none':
                    bits.append(regime)
                return '<b>%s</b> — %s' % (_esc(p.name), ', '.join(bits))

            html = ['<div class="o_coop_settle">',
                    '<p class="o_coop_settle_who">Платит %s.<br/>Получает %s.</p>' % (who(payer), who(payee))]
            for verdict in ('ok', 'warn', 'deny', 'planned'):
                group = [r for r in rows if r['verdict'] == verdict]
                if not group:
                    continue
                html.append('<h5 class="o_coop_settle_%s">%s</h5><ul>' % (verdict, labels[verdict]))
                for r in group:
                    cost = (' <span class="o_coop_settle_cost">%s</span>' % _esc(r['cost'])) if r['cost'] and verdict != 'deny' else ''
                    html.append('<li><b>%s</b>%s' % (_esc(r['name']), cost))
                    if r['reasons']:
                        html.append('<ul>%s</ul>' % ''.join('<li>%s</li>' % _esc(x) for x in r['reasons']))
                    html.append('</li>')
                html.append('</ul>')
            html.append('<p class="o_coop_settle_note">Цена — сквозная: всё, что уходит в бюджет с обеих '
                        'сторон вместе. Правила — из разбора юриста 22.09; перечень недружественных '
                        'государств — %s.</p></div>' % _esc(UNFRIENDLY_BASIS))
            deal.coop_settlement_html = ''.join(html)


def _esc(text):
    return (str(text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
