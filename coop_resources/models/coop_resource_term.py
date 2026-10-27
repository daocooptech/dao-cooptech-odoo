# -*- coding: utf-8 -*-
"""Условия объявления по способу передачи.

Решение 412 (Н5), владелец 25 сентября 2026: «надо добавить условия для
продажи, для аренды, для бартера и т. п.». У продажи и аренды одной вещи
разная цена, у аренды — залог и срок, у обмена — что возьмёшь взамен;
одна цена на всё объявление этого не выражает.

Строка условий — на каждый отмеченный способ; заводится и снимается сама,
вслед за «Способами передачи».
"""
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopResourceTerm(models.Model):
    _name = 'coop.resource.term'
    _description = 'Условия объявления по способу передачи'
    _order = 'sequence, id'

    resource_id = fields.Many2one('coop.resource', string='Объявление', required=True,
                                  ondelete='cascade', index=True)
    method_id = fields.Many2one('coop.resource.method', string='Способ', required=True,
                                ondelete='cascade')
    code = fields.Char(related='method_id.code', store=True)
    sequence = fields.Integer(related='method_id.sequence', store=True)
    is_monetary = fields.Boolean(related='method_id.is_monetary')
    currency_id = fields.Many2one(related='resource_id.currency_id')
    # «от / до / ровно / по договорённости» — у каждого способа своё
    # (владелец 27.10.2026: «цена настраивается в каждой вкладке»).
    price_kind = fields.Selection([
        ('from', 'от'),
        ('to', 'до'),
        ('exact', 'ровно'),
        ('none', 'по договорённости'),
    ], string='Уточнение цены', default='exact', required=True)
    price = fields.Monetary(string='Цена')
    price_unit_label = fields.Char(string='За что', help='шт., кг, сутки, месяц')
    deposit = fields.Monetary(string='Залог')
    min_term = fields.Char(string='Срок', help='Минимальный срок аренды, рассрочки, лизинга.')
    note = fields.Char(string='Условия')

    # Свои поля у каждого способа — решение 629, владелец 27.10.2026:
    # «продумай какие данные нужно вносить во вкладках продажа, аренда,
    # лизинг и тд.» Пустое не показывается (Н6), поэтому у выборов нет
    # значения по умолчанию, кроме периодичности платежей.
    # Продажа
    min_qty = fields.Float(string='Наименьшая партия')
    bulk_qty = fields.Float(string='Опт от')
    bulk_price = fields.Monetary(string='Оптовая цена')
    prepay_pct = fields.Integer(string='Предоплата, %')
    warranty = fields.Char(string='Гарантия')
    # Варианты — по разбору `accountant` 27.10.2026: «без документов»
    # только у человека без ИП, у организации — чек или первичный документ.
    documents = fields.Selection([
        ('none', 'без документов'),
        ('receipt', 'чек ККТ'),
        ('npd', 'чек самозанятого'),
        ('upd', 'УПД'),
        ('act', 'накладная или акт'),
    ], string='Документы')
    vat = fields.Selection([
        ('none', 'без НДС'),
        ('5', '5 %'),
        ('7', '7 %'),
        ('10', '10 %'),
        ('22', '22 %'),
    ], string='НДС')
    # Аренда
    max_term = fields.Char(string='Наибольший срок')
    operator = fields.Selection([
        ('no', 'без оператора'),
        ('yes', 'с оператором'),
        ('option', 'оператор за доплату'),
    ], string='Оператор')
    included = fields.Char(string='Входит в цену', help='Метки через запятую: топливо, расходники, доставка.')
    available_from = fields.Date(string='Свободно с')
    long_discount = fields.Char(string='Скидка за длинный срок')
    # Рассрочка и лизинг
    down_pct = fields.Float(string='Первый взнос, %')
    months = fields.Integer(string='Срок, месяцев')
    pay_every = fields.Selection([
        ('week', 'раз в неделю'),
        ('month', 'раз в месяц'),
        ('quarter', 'раз в квартал'),
    ], string='Платежи', default='month')
    markup_pct = fields.Float(string='Наценка, %')
    ownership = fields.Selection([
        ('now', 'сразу'),
        ('end', 'после последнего платежа'),
    ], string='Право собственности переходит')
    buyout = fields.Monetary(string='Выкупная стоимость')
    payment_manual = fields.Monetary(string='Платёж в месяц, вручную')
    lessor = fields.Selection([
        ('self', 'я сам'),
        ('partner', 'партнёрская лизинговая компания'),
    ], string='Лизингодатель')
    lessor_name = fields.Char(string='Лизинговая компания')
    # Лизингодатель покупает вещь «у определенного им продавца» (ГК ст. 665).
    seller_name = fields.Char(string='Продавец предмета')
    insurance = fields.Selection([
        ('lessee', 'лизингополучатель'),
        ('lessor', 'лизингодатель'),
        ('none', 'без страховки'),
    ], string='Страховку платит')
    payment = fields.Monetary(string='Платёж за период', compute='_compute_payment')
    total = fields.Monetary(string='Всего заплатить', compute='_compute_payment')
    # Участие в проекте
    contribution = fields.Selection([
        ('own', 'насовсем в проект'),
        ('use', 'в пользование на срок проекта'),
    ], string='Как вношу')
    expect = fields.Selection([
        ('share', 'долю'),
        ('product', 'часть продукции'),
        ('costs', 'возмещение расходов'),
    ], string='Что жду взамен')
    project_scope = fields.Char(string='В какие проекты')
    # В пользование — доля от арендной стоимости: ставка × срок
    # (`coop-economist` 27.10.2026); срок — `months`.
    use_rate = fields.Monetary(string='Ставка в месяц')
    repairs = fields.Selection([
        ('owner', 'я'),
        ('project', 'проект'),
    ], string='Кто чинит')
    wear = fields.Char(string='Нормальный износ')
    loss = fields.Selection([
        ('compensate', 'проект возмещает стоимость'),
        ('own', 'вклад переходит в «насовсем»'),
    ], string='При утрате')
    use_value = fields.Monetary(string='Вклад для доли', compute='_compute_payment')
    # Обмен
    surcharge = fields.Selection([
        ('none', 'без доплаты'),
        ('pay', 'готов доплатить'),
        ('want', 'жду доплату'),
    ], string='Доплата')
    surcharge_amount = fields.Monetary(string='Сумма доплаты')
    # Безвозмездно
    free_mode = fields.Selection([
        ('forever', 'насовсем'),
        ('loan', 'на время, с возвратом'),
    ], string='Отдаю')
    free_to = fields.Selection([
        ('any', 'любому'),
        ('org', 'организациям'),
        ('project', 'проектам'),
    ], string='Кому')

    summary = fields.Char(string='Кратко', compute='_compute_summary')

    _one_per_method = models.Constraint('unique(resource_id, method_id)',
                                        'Условия этого способа уже есть.')

    PERIODS_PER_MONTH = {'week': 52 / 12, 'month': 1, 'quarter': 1 / 3}

    @api.depends('code', 'price', 'down_pct', 'months', 'pay_every', 'markup_pct',
                 'buyout', 'payment_manual', 'contribution', 'use_rate')
    def _compute_payment(self):
        """Рассрочка: остаток после первого взноса с наценкой — равными
        платежами. Лизинг: стоимость без аванса и выкупа с удорожанием —
        по месяцам; платёж, введённый вручную, главнее расчётного."""
        for term in self:
            payment = total = 0.0
            if term.code in ('installment', 'leasing') and term.price and term.months > 0:
                down = term.price * (term.down_pct or 0) / 100
                markup = 1 + (term.markup_pct or 0) / 100
                if term.code == 'installment':
                    periods = max(1, round(term.months * self.PERIODS_PER_MONTH[term.pay_every or 'month']))
                    rest = (term.price - down) * markup
                    payment = rest / periods
                    total = down + rest
                else:
                    payment = term.payment_manual or \
                        max(0.0, term.price - down - (term.buyout or 0)) * markup / term.months
                    total = down + payment * term.months + (term.buyout or 0)
            term.payment = round(payment)
            term.total = round(total)
            term.use_value = (term.use_rate or 0) * (term.months or 0)                 if term.code == 'project' and term.contribution == 'use' else 0

    @staticmethod
    def _rub(value):
        return '{:,.0f} ₽'.format(value).replace(',', ' ')

    @staticmethod
    def _qty(value):
        return ('%g' % value).replace('.', ',')

    def _label(self, name):
        return dict(self._fields[name]._description_selection(self.env)).get(self[name])

    @api.depends('price', 'price_kind', 'price_unit_label', 'deposit', 'min_term', 'note', 'method_id',
                 'min_qty', 'bulk_qty', 'bulk_price', 'prepay_pct', 'warranty', 'documents',
                 'max_term', 'operator', 'included', 'available_from', 'long_discount',
                 'down_pct', 'months', 'pay_every', 'markup_pct', 'ownership', 'buyout',
                 'payment_manual', 'lessor', 'lessor_name', 'insurance', 'contribution', 'expect',
                 'project_scope', 'surcharge', 'surcharge_amount', 'free_mode', 'free_to',
                 'vat', 'seller_name', 'use_rate', 'repairs', 'loss')
    def _compute_summary(self):
        for term in self:
            term.summary = '; '.join(term._coop_summary_parts())

    def _coop_summary_parts(self, with_price=True):
        """Условия словами. Без цены — для витрины, где цена стоит
        отдельно крупно над условиями и второй раз её не пишут."""
        self.ensure_one()
        term = self
        prefix = {'from': 'от ', 'to': 'до ', 'exact': ''}
        parts = []
        code = term.code
        if code == 'barter' and term.note:
            parts.append('взамен: %s' % term.note)
        if not with_price:
            pass
        elif term.price_kind == 'none':
            parts.append('по договорённости')
        elif term.price:
            amount = prefix.get(term.price_kind, '') + term._rub(term.price)
            parts.append('%s за %s' % (amount, term.price_unit_label)
                         if term.price_unit_label else amount)
        if code == 'sale':
            if term.min_qty:
                parts.append('партия от %s' % term._qty(term.min_qty))
            if term.bulk_qty and term.bulk_price:
                parts.append('опт от %s — %s' % (term._qty(term.bulk_qty), term._rub(term.bulk_price)))
            if term.prepay_pct:
                parts.append('предоплата %s %%' % term.prepay_pct)
            if term.warranty:
                parts.append('гарантия %s' % term.warranty)
            if term.documents:
                parts.append(term._label('documents'))
            if term.vat:
                parts.append('НДС %s' % term._label('vat') if term.vat != 'none' else 'без НДС')
        if term.deposit:
            parts.append('залог %s' % term._rub(term.deposit))
        # У рассрочки и лизинга срок — в месяцах (`months`); прежний
        # текстовый срок показываем, только пока месяцев нет.
        min_term = term.min_term if not (code in ('installment', 'leasing') and term.months) else False
        if min_term and term.max_term:
            parts.append('срок %s – %s' % (min_term, term.max_term))
        elif min_term:
            parts.append('срок %s' % min_term)
        elif term.max_term:
            parts.append('срок не больше: %s' % term.max_term)
        if code == 'rent':
            if term.operator:
                parts.append(term._label('operator'))
            if term.included:
                parts.append('в цене: %s' % term.included)
            if term.available_from:
                parts.append('свободно с %s' % term.available_from.strftime('%d.%m.%Y'))
            if term.long_discount:
                parts.append('скидка: %s' % term.long_discount)
        if code in ('installment', 'leasing'):
            if term.down_pct:
                parts.append('%s %g %%' % ('первый взнос' if code == 'installment' else 'аванс',
                                           term.down_pct))
            if term.months:
                parts.append('на %s мес.' % term.months)
            if term.payment:
                every = 'в месяц' if code == 'leasing' else \
                    {'week': 'в неделю', 'quarter': 'в квартал'}.get(term.pay_every, 'в месяц')
                parts.append('%s %s' % (term._rub(term.payment), every))
            if code == 'installment':
                parts.append('без наценки' if not term.markup_pct else 'наценка %g %%' % term.markup_pct)
                if term.ownership:
                    parts.append('право собственности — %s' % term._label('ownership'))
            else:
                if term.buyout:
                    parts.append('выкуп %s' % term._rub(term.buyout))
                if term.lessor == 'partner':
                    parts.append('через %s' % (term.lessor_name or 'лизинговую компанию'))
                elif term.lessor == 'self' and term.seller_name:
                    parts.append('покупаю у %s' % term.seller_name)
                if term.insurance:
                    parts.append('страховка — %s' % term._label('insurance'))
        if code == 'project':
            if term.contribution:
                parts.append(term._label('contribution'))
            if term.contribution == 'use':
                if term.months:
                    parts.append('на %s мес.' % term.months)
                if term.use_rate:
                    parts.append('ставка %s в месяц' % term._rub(term.use_rate))
                if term.repairs:
                    parts.append('чинит %s' % term._label('repairs'))
                if term.loss:
                    parts.append('при утрате — %s' % term._label('loss'))
            if term.expect:
                parts.append('взамен — %s' % term._label('expect'))
            if term.project_scope:
                parts.append('проекты: %s' % term.project_scope)
        if code == 'barter' and term.surcharge in ('pay', 'want'):
            parts.append(term._label('surcharge') + (
                ' %s' % term._rub(term.surcharge_amount) if term.surcharge_amount else ''))
        if code == 'free':
            if term.free_mode:
                parts.append(term._label('free_mode'))
            if term.free_to:
                parts.append(term._label('free_to'))
        if term.note and code != 'barter':
            parts.append(term.note)
        return parts


class CoopResource(models.Model):
    _inherit = 'coop.resource'

    term_ids = fields.One2many('coop.resource.term', 'resource_id', string='Условия по способам')
    # Организации — без «без документов» и с НДС (`accountant` 27.10.2026).
    owner_is_company = fields.Boolean(related='owner_id.is_company', string='Владелец — организация')
    terms_html = fields.Html(string='Условия', compute='_compute_terms_html', sanitize=False)

    @api.depends('term_ids.summary', 'method_ids')
    def _compute_terms_html(self):
        """Опубликованное показывает только выбранное (Н6): способы, которые
        владелец отметил, и только заполненные условия — без пустых строк
        и без вариантов, которых он не выбирал."""
        for resource in self:
            rows = []
            for term in resource.term_ids.sorted('sequence'):
                rows.append(Markup('<li><b>%s</b>%s</li>') % (
                    term.method_id.name,
                    Markup(' — %s') % term.summary if term.summary else ''))
            resource.terms_html = Markup('<ul class="o_coop_res_terms">%s</ul>') % \
                Markup('').join(rows) if rows else False

    # Переключатель способа на витрине (дизайн-система, `ResourcePage`,
    # `Segmented`): у каждого способа своя цена, свои условия и своя
    # подпись отклика. Собираем здесь, чтобы подписи и цена считались тем
    # же кодом, что окно отклика и карточка в каталоге.
    way_cards = fields.Json(string='Способы на витрине', compute='_compute_way_cards')

    @api.depends('term_ids.price', 'term_ids.price_kind', 'term_ids.price_unit_label',
                 'term_ids.summary', 'method_ids', 'listing_type', 'price_display')
    def _compute_way_cards(self):
        prefix = {'from': 'от ', 'to': 'до ', 'exact': ''}
        for resource in self:
            cards = []
            for method in resource.method_ids.sorted('sequence'):
                term = resource.term_ids.filtered(lambda t: t.method_id == method)[:1]
                if term and term.price_kind == 'none':
                    price = 'по договорённости'
                elif term and term.price:
                    price = prefix.get(term.price_kind, '') + term._rub(term.price)
                    if term.price_unit_label:
                        price += ' / %s' % term.price_unit_label
                elif method.code == 'free':
                    price = 'даром'
                else:
                    price = resource.price_display
                cards.append({
                    'id': method.id,
                    'code': method.code,
                    'name': method.name,
                    'price': price,
                    'terms': '; '.join(term._coop_summary_parts(with_price=False)) if term else '',
                    'cta': resource._coop_respond_label(method),
                })
            resource.way_cards = cards

    def _coop_sync_terms(self):
        """Строка условий на каждый отмеченный способ — не больше и не меньше."""
        Term = self.env['coop.resource.term'].sudo()
        for resource in self:
            have = resource.term_ids
            wanted = resource.method_ids
            have.filtered(lambda t: t.method_id not in wanted).sudo().unlink()
            missing = wanted - have.method_id
            if missing:
                Term.create([{'resource_id': resource.id, 'method_id': method.id}
                             for method in missing])

    def _coop_price_from_terms(self):
        """Цена на карточке — из первого способа, где она указана.

        Владелец 27.10.2026: условия вносятся во вкладках способов, «ни
        каких таблиц» — значит и цену второй раз отдельным полем не
        спрашиваем. Каталог, фильтр по цене и проверка «нужна цена»
        по-прежнему читают `price` объявления — оно заполняется отсюда.
        """
        for resource in self:
            # Оценка дара — для учёта, не цена: «Безвозмездно» на карточке
            # с суммой читалось бы как продажа.
            priced = resource.term_ids.filtered(
                lambda t: t.code != 'free' and (t.price or t.price_kind == 'none')
            ).sorted('sequence')[:1]
            if not priced:
                continue
            values = {}
            if resource.price_kind != priced.price_kind:
                values['price_kind'] = priced.price_kind
            # «По договорённости» — без суммы на объявлении: её читает
            # фильтр каталога по цене. Во вкладке сумма остаётся.
            price = 0 if priced.price_kind == 'none' else priced.price
            if resource.price != price:
                values['price'] = price
            # Единица — того же способа, даже пустая: иначе цена продажи
            # получала бы «/сутки» от аренды.
            unit = priced.price_unit_label or False
            if (resource.price_unit_label or False) != unit:
                values['price_unit_label'] = unit
            if values:
                resource.with_context(coop_no_price_sync=True).write(values)

    def _coop_terms_problems(self):
        """Чего не хватает условиям, чтобы договор по ним состоялся.

        Разборы 27.10.2026 (решение 629): `legal-counsel` — рассрочка без
        срока и платежей не договор (ГК ст. 489 п. 1), лизингодатель
        покупает вещь у продавца (ГК ст. 665), аренда с экипажем — только
        транспорт (ГК ст. 632) — владелец 27.10.2026: «оставить без проверки»; `coop-economist` — вклад в пользование без
        срока, ставки, ремонта и утраты не даёт посчитать долю;
        `accountant` — организации нужны документы и НДС, оценка дара
        организациям и мены. Спрос проверяется мягче: условия там пишет
        тот, кто предложит.
        """
        self.ensure_one()
        problems = []
        offer = self.listing_type != 'request'
        company = self.owner_id.is_company
        for term in self.term_ids:
            name = term.method_id.name
            if term.code == 'installment':
                if self.resource_type == 'financial':
                    problems.append(_('«%(method)s»: деньги в рассрочку не продаются — это заём, его выдают '
                                      'только банки и финансовые организации.', method=name))
                if offer and not (term.months > 0 and term.pay_every):
                    problems.append(_('«%(method)s»: укажите срок в месяцах и как часто платить — без '
                                      'порядка и сроков платежей договор не заключён.', method=name))
            if term.code == 'leasing' and offer and term.lessor == 'self' and not term.seller_name:
                problems.append(_('«%(method)s»: лизингодатель покупает вещь у продавца — укажите продавца '
                                  'или сдайте свою вещь через «Аренду».', method=name))
            if term.code == 'project' and offer and term.contribution == 'use' and not (
                    term.months > 0 and term.use_rate and term.repairs and term.wear and term.loss):
                problems.append(_('«%(method)s»: в пользование — нужны срок, ставка в месяц, кто чинит, '
                                  'нормальный износ и что при утрате.', method=name))
            if term.code == 'sale' and offer and company:
                if not term.documents or term.documents == 'none':
                    problems.append(_('«%(method)s»: организация продаёт с документами — выберите чек '
                                      'или первичный документ.', method=name))
                if not term.vat:
                    problems.append(_('«%(method)s»: укажите НДС или «без НДС».', method=name))
            if term.code == 'free' and offer and term.free_to == 'org' and not term.price:
                problems.append(_('«%(method)s»: для организаций нужна оценка — у них это доход по '
                                  'рыночной цене.', method=name))
            if term.code == 'barter' and company and not term.price and term.price_kind != 'none':
                problems.append(_('«%(method)s»: организации нужна оценка своей вещи — мена для неё '
                                  'продажа.', method=name))
        return problems

    def action_publish(self):
        for record in self:
            problems = record._coop_terms_problems()
            if problems:
                raise UserError('\n'.join(problems))
        return super().action_publish()

    @api.model_create_multi
    def create(self, vals_list):
        resources = super().create(vals_list)
        resources.filtered('method_ids')._coop_sync_terms()
        resources.filtered('term_ids')._coop_price_from_terms()
        return resources

    def write(self, vals):
        result = super().write(vals)
        if 'method_ids' in vals:
            self._coop_sync_terms()
        if 'term_ids' in vals and not self.env.context.get('coop_no_price_sync'):
            self._coop_price_from_terms()
        return result
