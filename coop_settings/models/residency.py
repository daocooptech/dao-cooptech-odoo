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
разбор бухгалтера). Перечень 430-р — данные с датой и основанием, а не
константа в коде.

Слов «недружественное государство» на экранах платформы нет (решение 427).
Общего значка «Сделки временно недоступны» (решение 428) больше нет
(решение 500, владелец 26.10.2026: «как в указах»): с 01.10.2026 платформа
не вправе ограничивать доступ, кроме случаев, прямо названных законом
(ч. 2 ст. 3 289-ФЗ), а само 430-р ничего не запрещает. Закрываются только
виды сделок, которые ограничивают указы, — и только по гражданству и месту
регистрации стороны (Указ № 95, п. 1), а не по стране проживания. Внутренние
имена полей остались прежними — их никто не читает.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError

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

# Что закрывают указы (решение 500). Тексты прочитаны 26.10.2026:
# Указ № 81 — base.garant.ru/403590982, Указ № 95 — consultant.ru,
# cons_doc_LAW_410994. Ценных бумаг на платформе нет, а займы и
# недвижимость — есть: кредитная сделка и продажа объекта недвижимости.
DECREE_81 = 'Указ Президента РФ от 01.03.2022 № 81'
DECREE_95 = 'Указ Президента РФ от 05.03.2022 № 95'
DECREE_95_LIMIT = 10_000_000        # Указ № 95, п. 2: свыше 10 млн ₽ в месяц
REAL_ESTATE_ROOT = 'Недвижимость'   # корень дерева категорий ресурсов
# Способы, при которых у получателя возникает право собственности.
OWNERSHIP_WAYS = ('sale', 'purchase', 'batch', 'exchange', 'gift')

REGISTRATION_THRESHOLD = 3_000_000  # постановка контракта на учёт, Инструкция ЦБ 181-И
GIFT_LIMIT = 3000                   # п. 1 ст. 575 ГК

class ResCountry(models.Model):
    _inherit = 'res.country'

    coop_unfriendly = fields.Boolean(
        string='В перечне 430-р',
        help='Само распоряжение ничего не запрещает. С гражданами этой страны '
             'и организациями, зарегистрированными в ней, указы № 81 и № 95 '
             'ограничивают отдельные сделки: займы, недвижимость, ценные '
             'бумаги. Остальные сделки проводятся как обычно. Перечень '
             'меняется; основание и дата — рядом.')
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

    @api.model
    def _coop_fill_citizenship(self):
        """Гражданство тем, у кого его нет (решение 500), — при каждом
        обновлении, только пустым. Валютный резидент-человек — гражданин
        РФ: так его и записывали (ФЗ-173), иностранцев с ВНЖ поправляют
        вручную; нерезидент — гражданин страны, где живёт; организация —
        страна регистрации, она же страна из карточки."""
        russia = self.env.ref('base.ru', raise_if_not_found=False)
        empty = self.sudo().with_context(tracking_disable=True).search([
            ('coop_citizenship_id', '=', False),
            '|', ('coop_is_participant', '=', True), ('is_company', '=', True)])
        for partner in empty:
            if partner.is_company or not partner.coop_fx_resident:
                country = partner.country_id or russia
            else:
                country = russia
            if country:
                partner.coop_citizenship_id = country
        return True

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

    def _coop_rub_only(self):
        """Гражданин РФ — валютный резидент, где бы ни жил; российская
        организация — тоже (ФЗ-173). Иностранец с ВНЖ в РФ — резидент и
        считает в рублях; живущий в России без ВНЖ — выбирает сам."""
        self.ensure_one()
        return bool(self.coop_fx_resident)

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

    # Кто платит — `coop.deal._coop_payer_payee` в coop_deals: по ролям
    # сторон, затем по способу сделки (решение 427). То же правило ведёт
    # график платежей, и вкладка с графиком не расходится.

    def _coop_decree_block(self):
        """Чем закрыта сделка по указам — или пустая строка (решение 500).

        Указы ограничивают сделки резидента с лицом, связанным со страной
        перечня 430-р, — по гражданству и месту регистрации (Указ № 81,
        п. 1 «а»; Указ № 95, п. 1). Закрыты три случая:
        - заём такому лицу от резидента — только с разрешения
          Правительственной комиссии (Указ № 81, п. 1 «а», абз. 2, «б»);
        - возврат займа такому лицу свыше 10 млн ₽ — через счёт типа «С»
          (Указ № 95, пп. 1–3);
        - право собственности на недвижимость — только с разрешения
          Правительственной комиссии (Указ № 81, п. 1 «а», абз. 3, «б»).
        Разрешений Правительственной комиссии и счетов «С» платформа не
        ведёт, поэтому такие сделки не проводит. Остальное — как обычно."""
        self.ensure_one()
        if not self.party_a_id or not self.party_b_id:
            return ''
        payer, payee = self._coop_payer_payee()

        def listed(p):
            return p._coop_citizenship().coop_unfriendly

        def pair(foreign, resident):
            return listed(foreign) and not listed(resident) and resident.coop_fx_resident

        def country(p):
            return p._coop_citizenship().name
        credit = self.way == 'credit' or self.subject == 'credit'
        # В кредитной сделке платит заёмщик, получает кредитор.
        if credit and pair(payer, payee):
            return ('Заём участнику — гражданину или организации страны «%s» резидент РФ '
                    'может дать только с разрешения Правительственной комиссии по контролю '
                    'за осуществлением иностранных инвестиций (%s, п. 1 «а», «б»). '
                    'Таких разрешений платформа не оформляет, поэтому кредитную сделку '
                    'не проводит. Остальные сделки с этим участником — как обычно.'
                    % (country(payer), DECREE_81))
        if credit and pair(payee, payer) and (self.amount or 0.0) > DECREE_95_LIMIT:
            return ('Возврат займа кредитору — гражданину или организации страны «%s» — '
                    'свыше 10 млн ₽ в месяц идёт только через счёт типа «С» (%s, пп. 1–3). '
                    'Таких счетов платформа не ведёт, поэтому кредитную сделку на эту '
                    'сумму не проводит. До 10 млн ₽ и все остальные сделки — как обычно.'
                    % (country(payee), DECREE_95))
        category = self.resource_id.category_id
        estate = category and (category.complete_name or '').split(' / ')[0] == REAL_ESTATE_ROOT
        if estate and self.way in OWNERSHIP_WAYS and (pair(payer, payee) or pair(payee, payer)):
            foreign = payer if listed(payer) else payee
            return ('Сделку, по которой возникает право собственности на недвижимость, с '
                    'гражданином или организацией страны «%s» резидент РФ может совершить '
                    'только с разрешения Правительственной комиссии по контролю за '
                    'осуществлением иностранных инвестиций (%s, п. 1 «а», «б»). Таких '
                    'разрешений платформа не оформляет, поэтому эту сделку не проводит. '
                    'Аренда и остальные сделки — как обычно.' % (country(foreign), DECREE_81))
        return ''

    def action_agree(self):
        """Сделку, закрытую указом, не согласовать (решение 500): объяснение
        — тем же текстом, что во вкладке «Как рассчитаться»."""
        for record in self:
            block = record._coop_decree_block()
            if block:
                raise UserError(block)
        return super().action_agree()

    @api.depends('party_a_id', 'party_b_id', 'way', 'subject', 'amount', 'role_a', 'role_b',
                 'resource_id', 'payment_ids.payer_id', 'payment_ids.payee_id')
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
                # Гражданство — когда оно не совпадает со страной: по нему,
                # а не по проживанию, считают указы (решение 500).
                citizenship = p._coop_citizenship()
                if citizenship and citizenship != p.country_id:
                    bits.append('%s — %s' % ('регистрация' if p.is_company else 'гражданство',
                                             citizenship.name))
                regime = dict(p._fields['coop_tax_regime']._description_selection(p.env)).get(p.coop_tax_regime)
                if regime and p.coop_tax_regime != 'none':
                    bits.append(regime)
                return '<b>%s</b> — %s' % (_esc(p.name), ', '.join(bits))

            html = ['<div class="o_coop_settle">',
                    '<p class="o_coop_settle_who">Платит %s.<br/>Получает %s.</p>' % (who(payer), who(payee))]
            block = deal._coop_decree_block()
            if block:
                # Способы перечислять незачем: сделка не проводится.
                html.append('<p class="o_coop_settle_block"><b>Эту сделку платформа не '
                            'проводит</b><br/>%s</p></div>' % _esc(block))
                deal.coop_settlement_html = ''.join(html)
                continue
            listed = [p for p in (payer, payee) if p._coop_citizenship().coop_unfriendly]
            if listed:
                html.append('<p class="o_coop_settle_note">%s — из страны перечня по '
                            'распоряжению Правительства РФ от 05.03.2022 № 430-р. Указы № 81 и '
                            '№ 95 ограничивают с такими участниками только займы, сделки с '
                            'недвижимостью и ценными бумагами; эта сделка к ним не относится.</p>'
                            % _esc(', '.join(p.name for p in listed)))
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
                        'сторон вместе. Правила — из разбора юриста 22.09.</p></div>')
            deal.coop_settlement_html = ''.join(html)


def _esc(text):
    return (str(text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
