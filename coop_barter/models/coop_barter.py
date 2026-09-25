# -*- coding: utf-8 -*-
"""Бартер — объявления «отдаю — хочу взамен», подбор и обмен.

Решение 412 (Н7) и разбор площадок: `Матчасть/2026-09-25 — Бартерные
площадки — Бартерон и другие, что берём`.
"""
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Сколько цепочек на троих показывать за раз: перебор растёт как квадрат
# числа объявлений, а человеку больше десятка вариантов не нужно.
CHAIN_LIMIT = 10


class CoopBarterCategory(models.Model):
    """Категория обмена — метка «что это» и «что приму взамен».

    Как метки у «Бартерона»: одна и та же категория стоит и у того, что
    человек отдаёт, и у того, что он хочет, — по совпадению меток и
    ищутся встречные обмены.
    """
    _name = 'coop.barter.category'
    _description = 'Категория обмена'
    _order = 'sequence, id'

    name = fields.Char(string='Название', required=True)
    code = fields.Char(string='Код', required=True)
    icon = fields.Char(string='Значок')
    sequence = fields.Integer(string='Порядок', default=10)
    is_service = fields.Boolean(string='Услуги',
                                help='Работа и услуги: состояния вещи у них нет.')
    offer_count = fields.Integer(compute='_compute_offer_count')

    _code_unique = models.Constraint('unique(code)', 'Такая категория уже есть.')

    def _compute_offer_count(self):
        data = self.env['coop.barter.offer']._read_group(
            [('state', '=', 'active'), ('category_id', 'in', self.ids)],
            ['category_id'], ['__count'])
        counts = {category.id: count for category, count in data}
        for category in self:
            category.offer_count = counts.get(category.id, 0)


class CoopBarterOffer(models.Model):
    """Объявление об обмене: что отдаю и что хочу взамен."""
    _name = 'coop.barter.offer'
    _description = 'Объявление об обмене'
    _inherit = ['mail.thread']
    _order = 'published_on desc, id desc'

    name = fields.Char(string='Что отдаю', required=True, tracking=True)
    description = fields.Text(string='Подробности')
    partner_id = fields.Many2one('res.partner', string='Кто меняет', required=True, index=True,
                                 default=lambda self: self.env.user.partner_id)
    city = fields.Char(string='Город', index=True)
    category_id = fields.Many2one('coop.barter.category', string='Категория', required=True,
                                  index=True, ondelete='restrict')
    icon = fields.Char(related='category_id.icon')
    is_service = fields.Boolean(related='category_id.is_service')
    want_category_ids = fields.Many2many(
        'coop.barter.category', 'coop_barter_offer_want_rel', 'offer_id', 'category_id',
        string='Приму взамен',
        help='Категории, из которых подойдёт встречное предложение. По ним '
             'подбираются встречные обмены и цепочки.')
    want_text = fields.Char(string='Что хочу взамен', help='Своими словами, конкретнее категорий.')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.ref('base.RUB', raise_if_not_found=False))
    value = fields.Monetary(string='Оценка, ₽',
                            help='Во сколько вы оцениваете то, что отдаёте. Мена предполагается '
                                 'равноценной (ст. 568 ГК); оценка нужна, чтобы подобрать '
                                 'сопоставимый обмен и записать сделку.')
    surcharge_ok = fields.Boolean(string='Возможна доплата',
                                  help='Если оценки не совпали, разницу можно доплатить.')
    condition = fields.Selection([
        ('new', 'Новое'), ('good', 'Хорошее'), ('used', 'Б/у'),
    ], string='Состояние')
    quantity = fields.Char(string='Сколько', help='Например: 2 т, 40 мешков, 10 часов работы.')
    handover_pickup = fields.Boolean(string='Самовывоз', default=True)
    handover_delivery = fields.Boolean(string='Привезу')
    handover_post = fields.Boolean(string='Отправлю почтой или ТК')
    resource_id = fields.Many2one(
        'coop.resource', string='Объявление в «Ресурсах»', index=True, ondelete='set null',
        help='Если вещь уже выставлена в «Ресурсах», — оттуда фото, и после обмена '
             'запись попадёт в историю прав ресурса.')
    state = fields.Selection([
        ('draft', 'Черновик'),
        ('active', 'Меняю'),
        ('reserved', 'Идёт обмен'),
        ('done', 'Обменяно'),
        ('closed', 'Снято'),
    ], string='Состояние', default='active', required=True, index=True, tracking=True)
    published_on = fields.Datetime(string='Опубликовано', default=fields.Datetime.now, index=True)

    has_photo = fields.Boolean(compute='_compute_labels')
    value_label = fields.Char(compute='_compute_labels')
    want_label = fields.Char(compute='_compute_labels')
    handover_label = fields.Char(compute='_compute_labels')
    is_mine = fields.Boolean(compute='_compute_is_mine', search='_search_is_mine')
    fits_me = fields.Boolean(compute='_compute_fits_me', search='_search_fits_me',
                             string='Подходит мне')
    leg_ids = fields.One2many('coop.barter.leg', 'offer_id', string='Участие в обменах')
    exchange_count = fields.Integer(compute='_compute_exchange_count')

    @api.depends('value', 'want_category_ids', 'want_text', 'handover_pickup',
                 'handover_delivery', 'handover_post', 'resource_id')
    def _compute_labels(self):
        for offer in self:
            offer.has_photo = bool(offer.resource_id)
            offer.value_label = ('≈ {:,.0f} ₽'.format(offer.value).replace(',', ' ')
                                 if offer.value else 'Без оценки')
            wants = offer.want_category_ids.mapped('name')
            offer.want_label = offer.want_text or ', '.join(wants) or 'Предложите'
            # Видно только выбранное (решение 412, Н6): «привезу» без
            # «почтой» — значит, почты нет, и писать это незачем.
            ways = [label for flag, label in (
                (offer.handover_pickup, 'самовывоз'), (offer.handover_delivery, 'привезу'),
                (offer.handover_post, 'почтой или ТК')) if flag]
            offer.handover_label = ', '.join(ways).capitalize()

    @api.depends('partner_id')
    def _compute_is_mine(self):
        mine = self.env.user.coop_actor_partner_ids
        for offer in self:
            offer.is_mine = offer.partner_id in mine

    def _search_is_mine(self, operator, value):
        positive = (operator == '=') == bool(value)
        return [('partner_id', 'in' if positive else 'not in',
                 self.env.user.coop_actor_partner_ids.ids)]

    def _my_wants(self):
        """Что хочу я — объединение «приму взамен» всех моих объявлений."""
        mine = self.sudo().search([('partner_id', 'in', self.env.user.coop_actor_partner_ids.ids),
                                   ('state', '=', 'active')])
        return mine.want_category_ids

    def _compute_fits_me(self):
        wants = self._my_wants()
        mine = self.env.user.coop_actor_partner_ids
        for offer in self:
            offer.fits_me = offer.category_id in wants and offer.partner_id not in mine

    def _search_fits_me(self, operator, value):
        positive = (operator == '=') == bool(value)
        wants = self._my_wants()
        domain = [('category_id', 'in', wants.ids),
                  ('partner_id', 'not in', self.env.user.coop_actor_partner_ids.ids)]
        return domain if positive else ['!', '&'] + domain

    def _compute_exchange_count(self):
        for offer in self:
            offer.exchange_count = len(offer.leg_ids.exchange_id)

    # ── Подбор ──────────────────────────────────────────────────────

    def _coop_pool(self):
        return self.sudo().search([('state', '=', 'active')])

    def _coop_direct(self, pool=None):
        """Встречные: у него то, что я хочу, и он хочет то, что есть у меня."""
        self.ensure_one()
        pool = pool if pool is not None else self._coop_pool()
        return pool.filtered(lambda o: o.partner_id != self.partner_id
                             and o.category_id in self.want_category_ids
                             and self.category_id in o.want_category_ids)

    def _coop_chains(self, pool=None):
        """Цепочки на троих, как у «Бартерона»: я отдаю B, B отдаёт C,
        C отдаёт мне. Каждому достаётся то, что он хочет, хотя ни одна
        пара напрямую не совпала."""
        self.ensure_one()
        pool = pool if pool is not None else self._coop_pool()
        # Кто даёт мне то, что я хочу: у C категория из моих желаний.
        givers = pool.filtered(lambda o: o.partner_id != self.partner_id
                               and o.category_id in self.want_category_ids)
        # Кто хочет то, что есть у меня: B.
        takers = pool.filtered(lambda o: o.partner_id != self.partner_id
                               and self.category_id in o.want_category_ids)
        chains = []
        for b in takers:
            for c in givers:
                if c.partner_id == b.partner_id or c.category_id not in b.want_category_ids:
                    continue
                # Прямой обмен лучше цепочки — его покажут отдельно.
                if self.category_id in c.want_category_ids:
                    continue
                gap = abs((self.value or 0) - (b.value or 0)) + abs((b.value or 0) - (c.value or 0))
                chains.append((gap, b, c))
        chains.sort(key=lambda row: (row[0], row[1].id, row[2].id))
        return [(b, c) for _gap, b, c in chains[:CHAIN_LIMIT]]

    def action_find_matches(self):
        """Подобрать обмен — встречные и цепочки на троих списком."""
        self.ensure_one()
        Match = self.env['coop.barter.match']
        Match.search([('offer_id', '=', self.id), ('create_uid', '=', self.env.uid)]).unlink()
        pool = self._coop_pool()
        rows = []
        for other in self._coop_direct(pool):
            rows.append({'offer_id': self.id, 'kind': 'direct', 'their_offer_id': other.id,
                         'gap': (other.value or 0) - (self.value or 0),
                         'same_city': bool(self.city) and other.city == self.city})
        for b, c in self._coop_chains(pool):
            rows.append({'offer_id': self.id, 'kind': 'chain', 'their_offer_id': b.id,
                         'third_offer_id': c.id, 'gap': (c.value or 0) - (self.value or 0),
                         'same_city': bool(self.city) and b.city == self.city == c.city})
        Match.create(rows)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Обмен для «%s»') % self.name,
            'res_model': 'coop.barter.match',
            'view_mode': 'list',
            'domain': [('offer_id', '=', self.id), ('create_uid', '=', self.env.uid)],
            'context': {'create': False},
            'target': 'current',
        }

    # ── Состояние ───────────────────────────────────────────────────

    def action_publish(self):
        self.write({'state': 'active', 'published_on': fields.Datetime.now()})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_open_exchanges(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Обмены'),
            'res_model': 'coop.barter.exchange',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.leg_ids.exchange_id.ids)],
        }

    def _coop_catalog_filters(self, domain):
        categories = self.env['coop.barter.category'].search([])
        options = [{'value': str(c.id), 'label': '%s %s' % (c.icon or '', c.name)} for c in categories]
        return [
            {'code': 'category', 'label': 'Что отдают', 'widget': 'select', 'field': 'category_id',
             'placeholder': 'Любое', 'options': options, 'number': True},
            {'code': 'want', 'label': 'Что возьмут взамен', 'widget': 'select',
             'field': 'want_category_ids', 'placeholder': 'Любое', 'options': options,
             'number': True},
            {'code': 'city', 'label': 'Город', 'widget': 'text', 'field': 'city',
             'operator': 'ilike', 'placeholder': 'Начните вводить город'},
            {'code': 'value', 'label': 'Оценка, ₽', 'widget': 'range', 'field': 'value'},
            {'code': 'condition', 'label': 'Состояние вещи', 'widget': 'select', 'field': 'condition',
             'placeholder': 'Любое', 'options': [
                 {'value': code, 'label': label}
                 for code, label in self._fields['condition'].selection]},
            {'code': 'quick', 'label': 'Быстрые фильтры', 'widget': 'quick', 'options': [
                {'value': 'fits', 'label': '🎯 Подходит мне', 'domain': [('fits_me', '=', True)]},
                {'value': 'delivery', 'label': '🚚 Привезут',
                 'domain': [('handover_delivery', '=', True)]},
                {'value': 'surcharge', 'label': '💱 Возможна доплата',
                 'domain': [('surcharge_ok', '=', True)]},
            ]},
        ]


class CoopBarterMatch(models.TransientModel):
    """Вариант обмена из подбора — строка списка с кнопкой «Предложить»."""
    _name = 'coop.barter.match'
    _description = 'Вариант обмена'
    _order = 'kind desc, same_city desc, abs_gap, id'

    offer_id = fields.Many2one('coop.barter.offer', string='Моё объявление', required=True,
                               ondelete='cascade')
    kind = fields.Selection([('direct', 'Встречный'), ('chain', 'Цепочка на троих')],
                            string='Как', required=True)
    their_offer_id = fields.Many2one('coop.barter.offer', string='Кому отдаю — и что он даёт',
                                     required=True, ondelete='cascade')
    third_offer_id = fields.Many2one('coop.barter.offer', string='Третий — что даёт мне',
                                     ondelete='cascade')
    gap = fields.Float(string='Разница оценок, ₽')
    abs_gap = fields.Float(compute='_compute_abs_gap', store=True)
    same_city = fields.Boolean(string='В моём городе')
    summary = fields.Char(string='Обмен', compute='_compute_summary')

    @api.depends('gap')
    def _compute_abs_gap(self):
        for match in self:
            match.abs_gap = abs(match.gap)

    def _compute_summary(self):
        for match in self:
            mine, their, third = match.offer_id, match.their_offer_id, match.third_offer_id
            if match.kind == 'direct':
                match.summary = _('Вы → %(who)s: «%(mine)s»; %(who)s → вам: «%(their)s»',
                                  who=their.partner_id.name, mine=mine.name, their=their.name)
            else:
                match.summary = _(
                    'Вы → %(b)s: «%(mine)s»; %(b)s → %(c)s: «%(their)s»; %(c)s → вам: «%(third)s»',
                    b=their.partner_id.name, c=third.partner_id.name,
                    mine=mine.name, their=their.name, third=third.name)

    def action_propose(self):
        self.ensure_one()
        exchange = self.env['coop.barter.exchange']._coop_propose(
            self.offer_id, self.their_offer_id, self.third_offer_id)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'coop.barter.exchange',
            'res_id': exchange.id,
            'view_mode': 'form',
            'target': 'current',
        }


class CoopBarterExchange(models.Model):
    """Обмен — договорённость двух или трёх участников.

    Когда согласились все, обмен раскладывается на сделки платформы вида
    «Обмен», по одной на каждую передачу: у бухгалтера мена — две
    реализации, и актов всегда не меньше двух. Дальше каждая сделка идёт
    своим ходом — акты обеих сторон, отзывы, история прав ресурса, —
    а обмен завершён, когда завершены все его сделки.
    """
    _name = 'coop.barter.exchange'
    _description = 'Обмен'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Номер', required=True, copy=False, readonly=True,
                       default=lambda self: _('Новый обмен'))
    kind = fields.Selection([('direct', 'Встречный'), ('chain', 'Цепочка на троих')],
                            string='Вид', required=True, default='direct')
    initiator_id = fields.Many2one('res.partner', string='Кто предложил', required=True,
                                   readonly=True, default=lambda self: self.env.user.partner_id)
    leg_ids = fields.One2many('coop.barter.leg', 'exchange_id', string='Кто кому что передаёт')
    participant_ids = fields.Many2many('res.partner', string='Участники',
                                       compute='_compute_participants', store=True)
    participant_label = fields.Char(string='Участники', compute='_compute_participants', store=True)
    state = fields.Selection([
        ('proposed', 'Предложен'),
        ('agreed', 'Исполняется'),
        ('done', 'Завершён'),
        ('declined', 'Отклонён'),
        ('cancelled', 'Отменён'),
    ], string='Состояние', default='proposed', required=True, index=True, tracking=True)
    note = fields.Text(string='Сообщение участникам')
    agreed_on = fields.Date(string='Согласован', readonly=True)
    closed_on = fields.Date(string='Закрыт', readonly=True)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.ref('base.RUB', raise_if_not_found=False))
    total_value = fields.Monetary(string='Сумма оценок', compute='_compute_values', store=True)
    value_gap = fields.Monetary(string='Наибольшая разница оценок', compute='_compute_values',
                                store=True)
    deal_ids = fields.One2many('coop.deal', 'coop_barter_exchange_id', string='Сделки')
    accepted_count = fields.Integer(compute='_compute_progress')
    progress_label = fields.Char(string='Ход', compute='_compute_progress')
    can_accept = fields.Boolean(compute='_compute_my')
    is_participant = fields.Boolean(compute='_compute_my', search='_search_is_participant')
    notice_html = fields.Html(compute='_compute_notice', sanitize=False)

    @api.depends('leg_ids.giver_id', 'leg_ids.receiver_id')
    def _compute_participants(self):
        for exchange in self:
            partners = exchange.leg_ids.giver_id | exchange.leg_ids.receiver_id
            exchange.participant_ids = partners
            exchange.participant_label = ', '.join(partners.mapped('name'))

    @api.depends('leg_ids.value')
    def _compute_values(self):
        for exchange in self:
            values = exchange.leg_ids.mapped('value')
            exchange.total_value = sum(values)
            exchange.value_gap = (max(values) - min(values)) if values else 0

    @api.depends('leg_ids.accepted', 'deal_ids.state')
    def _compute_progress(self):
        for exchange in self:
            legs = exchange.leg_ids
            exchange.accepted_count = len(legs.filtered('accepted'))
            if exchange.state == 'proposed':
                exchange.progress_label = _('Согласились %(n)s из %(total)s',
                                            n=exchange.accepted_count, total=len(legs))
            elif exchange.deal_ids:
                done = len(exchange.deal_ids.filtered(lambda d: d.state == 'done'))
                exchange.progress_label = _('Передач завершено %(n)s из %(total)s',
                                            n=done, total=len(exchange.deal_ids))
            else:
                exchange.progress_label = ''

    def _compute_my(self):
        mine = self.env.user.coop_actor_partner_ids
        for exchange in self:
            exchange.is_participant = bool(exchange.participant_ids & mine)
            exchange.can_accept = exchange.state == 'proposed' and bool(
                exchange.leg_ids.filtered(lambda l: l.giver_id in mine and not l.accepted))

    def _search_is_participant(self, operator, value):
        positive = (operator == '=') == bool(value)
        ids = self.env.user.coop_actor_partner_ids.ids
        return [('participant_ids', 'in' if positive else 'not in', ids)]

    def _compute_notice(self):
        """Что стоит знать до согласия — из разборов юриста и бухгалтера."""
        for exchange in self:
            partners = exchange.participant_ids
            lines = [Markup('<b>%s</b> %s') % (
                _('Мена — две продажи, а не одна.'),
                _('Каждая сторона признаёт доход в полной оценке того, что получила: '
                  'на УСН «доходы» — по 6 %% у каждой, 12 %% на двоих; если одна сторона '
                  'платит НДС, а вторая нет, — до 34 %%. Физлицо получает доход в '
                  'натуральной форме — НДФЛ 13 %%.'))]
            if any(p.is_company for p in partners) and any(not p.is_company for p in partners):
                lines.append(Markup('<b>%s</b> %s') % (
                    _('Нужен чек.'),
                    _('Организация или ИП, меняющиеся с физлицом, пробивают чек: встречное '
                      'предоставление — тоже расчёт (54-ФЗ).')))
            lines.append(Markup('<b>%s</b> %s') % (
                _('С нерезидентом — не здесь.'),
                _('Обмен с иностранной стороной — внешнеторговая бартерная сделка со '
                  'встречной поставкой в срок; её оформляют в «Международных сделках».')))
            exchange.notice_html = Markup('<div class="alert alert-info mb-3 o_coop_barter_notice">'
                                          '%s</div>') % Markup('<br/>').join(lines)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('Новый обмен'):
                vals['name'] = self.env['ir.sequence'].next_by_code('coop.barter.exchange') \
                    or _('Новый обмен')
        return super().create(vals_list)

    # ── Ход обмена ──────────────────────────────────────────────────

    @api.model
    def _coop_propose(self, mine, their, third=None):
        """Предложить обмен: встречный (двое) или цепочку (трое)."""
        if mine.partner_id not in self.env.user.coop_actor_partner_ids:
            raise UserError(_('Предложить обмен можно только своим объявлением.'))
        offers = mine | their | (third or self.env['coop.barter.offer'])
        if offers.filtered(lambda o: o.state != 'active'):
            raise UserError(_('Одно из объявлений уже не в обмене — подберите заново.'))
        if third:
            legs = [(mine, their.partner_id), (their, third.partner_id), (third, mine.partner_id)]
        else:
            legs = [(mine, their.partner_id), (their, mine.partner_id)]
        exchange = self.sudo().create({
            'kind': 'chain' if third else 'direct',
            'initiator_id': mine.partner_id.id,
            'leg_ids': [(0, 0, {'offer_id': offer.id, 'receiver_id': receiver.id,
                                'accepted': offer == mine,
                                'accepted_on': fields.Datetime.now() if offer == mine else False})
                        for offer, receiver in legs],
        })
        exchange.message_subscribe(partner_ids=exchange.participant_ids.ids)
        others = exchange.participant_ids - mine.partner_id
        self.env['coop.notification']._notify(
            others, _('%(who)s предлагает обмен %(number)s: %(what)s',
                      who=mine.partner_id.name, number=exchange.name, what=mine.name),
            record=exchange, kind='deal')
        return exchange

    def action_accept(self):
        """Согласиться со своей стороны. Когда согласны все — сделки."""
        mine = self.env.user.coop_actor_partner_ids
        for exchange in self:
            legs = exchange.leg_ids.filtered(lambda l: l.giver_id in mine and not l.accepted)
            if exchange.state != 'proposed' or not legs:
                raise UserError(_('Согласиться здесь нечего: обмен не ждёт вашего ответа.'))
            for leg in legs:
                leg.giver_id.coop_require_level('identity', _('меняться'))
            legs.sudo().write({'accepted': True, 'accepted_on': fields.Datetime.now()})
            if all(exchange.leg_ids.mapped('accepted')):
                exchange.sudo()._coop_make_deals()
            else:
                exchange.sudo().message_post(body=_('%s — согласен.') % ', '.join(
                    legs.giver_id.mapped('name')))
        return True

    def _coop_make_deals(self, date=None):
        """Разложить обмен на сделки «Обмен» — по одной на передачу."""
        Deal = self.env['coop.deal'].sudo()
        for exchange in self:
            today = date or fields.Date.context_today(exchange)
            for leg in exchange.leg_ids:
                offer = leg.offer_id
                leg.deal_id = Deal.create({
                    'name': offer.name,
                    'subject': 'service' if offer.is_service else 'resource',
                    'way': 'exchange',
                    'party_a_id': leg.giver_id.id,
                    'party_b_id': leg.receiver_id.id,
                    'role_a': _('Передаёт'),
                    'role_b': _('Получает'),
                    'author_id': exchange.initiator_id.id,
                    'city': offer.city,
                    'resource_id': offer.resource_id.id,
                    'amount': offer.value,
                    'state': 'agreed',
                    'signed_on': today,
                    'coop_barter_exchange_id': exchange.id,
                })
            exchange.leg_ids.offer_id.write({'state': 'reserved'})
            exchange.write({'state': 'agreed', 'agreed_on': today})
            exchange.message_post(body=_(
                'Все согласны. Обмен разложен на сделки «Обмен» — по одной на каждую '
                'передачу; акты подтверждают стороны каждой сделки.'))

    def _coop_sync_state(self):
        """Обмен завершён, когда завершены все его сделки."""
        for exchange in self.filtered(lambda e: e.state == 'agreed' and e.deal_ids):
            states = set(exchange.deal_ids.mapped('state'))
            if states == {'done'}:
                exchange.write({'state': 'done', 'closed_on': fields.Date.context_today(exchange)})
                exchange.leg_ids.offer_id.write({'state': 'done'})
            elif states <= {'cancelled', 'done'} and 'cancelled' in states:
                exchange.write({'state': 'cancelled',
                                'closed_on': fields.Date.context_today(exchange)})
                exchange._coop_release()

    def _coop_release(self):
        """Объявления, которые больше нигде не заняты, — снова в обмен."""
        for offer in self.leg_ids.offer_id.filtered(lambda o: o.state == 'reserved'):
            busy = offer.leg_ids.exchange_id.filtered(lambda e: e.state == 'agreed')
            if not busy:
                offer.state = 'active'

    def action_decline(self):
        mine = self.env.user.coop_actor_partner_ids
        for exchange in self:
            if exchange.state != 'proposed' or not (exchange.participant_ids & mine):
                raise UserError(_('Отклонить может участник предложенного обмена.'))
            exchange.sudo().write({'state': 'declined',
                                   'closed_on': fields.Date.context_today(exchange)})
            exchange.sudo().message_post(body=_('%s отклонил обмен.') % self.env.user.partner_id.name)
        return True

    def action_cancel(self):
        for exchange in self:
            if exchange.state != 'proposed' or exchange.initiator_id not in \
                    self.env.user.coop_actor_partner_ids:
                raise UserError(_('Отменить предложение может тот, кто его сделал, — '
                                  'пока остальные не согласились.'))
            exchange.sudo().write({'state': 'cancelled',
                                   'closed_on': fields.Date.context_today(exchange)})
        return True

    def action_open_deals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Сделки обмена %s') % self.name,
            'res_model': 'coop.deal',
            'view_mode': 'list,form',
            'domain': [('coop_barter_exchange_id', '=', self.id)],
        }


class CoopBarterLeg(models.Model):
    """Одна передача в обмене: кто, что и кому отдаёт."""
    _name = 'coop.barter.leg'
    _description = 'Передача в обмене'
    _order = 'exchange_id, id'

    exchange_id = fields.Many2one('coop.barter.exchange', string='Обмен', required=True,
                                  ondelete='cascade', index=True)
    offer_id = fields.Many2one('coop.barter.offer', string='Что передаётся', required=True,
                               ondelete='restrict', index=True)
    giver_id = fields.Many2one(related='offer_id.partner_id', store=True, string='Кто отдаёт')
    receiver_id = fields.Many2one('res.partner', string='Кому', required=True, index=True)
    currency_id = fields.Many2one(related='offer_id.currency_id')
    value = fields.Monetary(related='offer_id.value', store=True, string='Оценка, ₽')
    accepted = fields.Boolean(string='Согласен')
    accepted_on = fields.Datetime(string='Когда согласился')
    deal_id = fields.Many2one('coop.deal', string='Сделка', ondelete='set null')
    deal_state = fields.Selection(related='deal_id.state', string='Сделка — состояние')


class CoopDeal(models.Model):
    _inherit = 'coop.deal'

    coop_barter_exchange_id = fields.Many2one('coop.barter.exchange', string='Обмен',
                                              index=True, ondelete='set null')

    def write(self, vals):
        result = super().write(vals)
        if 'state' in vals:
            self.sudo().coop_barter_exchange_id._coop_sync_state()
        return result
