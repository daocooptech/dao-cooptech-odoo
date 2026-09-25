# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Ориентир лимита энергопотребления для физлица без ИП (разбор юриста,
# 2.4, со звёздочкой: лимит устанавливает Правительство, и он меняется).
PERSON_KWH_LIMIT = 6000

NOTICE = ('Майнинг законен при соблюдении режима: юрлица и ИП — в реестре '
          'ФНС; физлица без ИП — в пределах лимита энергопотребления '
          '(ориентир — 6000 кВт·ч в месяц); отчёт в ФНС о полученной '
          'цифровой валюте обязателен. Платформа намайненное на хранение не '
          'берёт и пулом не выступает.')


class CoopMiner(models.Model):
    """Майнер — участник платформы, который добывает цифровую валюту.

    Решение 392 и разбор юриста (2.4): майнинг — единственный участок
    крипторегулирования с ясной процедурой. Каталог показывает, у кого
    запись в реестре ФНС есть, у кого на рассмотрении, кому она не нужна
    (физлицо в пределах лимита), — и предупреждает, если физлицо лимит
    превышает.
    """
    _name = 'coop.miner'
    _description = 'Майнер'
    _inherit = ['mail.thread']
    _order = 'power_kw desc, id'

    partner_id = fields.Many2one('res.partner', string='Участник', required=True,
                                 index=True, default=lambda self: self.env.user.partner_id)
    name = fields.Char(related='partner_id.name', store=True, string='Кто')
    kind = fields.Selection([
        ('legal', 'Юрлицо'),
        ('ip', 'Индивидуальный предприниматель'),
        ('person', 'Физлицо без ИП'),
    ], string='Кто по форме', required=True, default='person', index=True)
    registry_state = fields.Selection([
        ('registered', 'В реестре ФНС'),
        ('pending', 'Заявление на рассмотрении'),
        ('not_required', 'Физлицо: реестр не нужен (до 6000 кВт·ч/мес)'),
        ('missing', 'Нужна запись в реестре'),
    ], string='Реестр ФНС', required=True, default='not_required', index=True, tracking=True)
    registry_number = fields.Char(string='Номер записи в реестре')
    registry_date = fields.Date(string='Включён в реестр')
    city = fields.Char(string='Город', index=True)
    region = fields.Char(string='Регион')
    energy_source = fields.Selection([
        ('grid', 'Сеть'),
        ('hydro', 'ГЭС'),
        ('gas', 'Попутный газ'),
        ('solar', 'Солнечная станция'),
    ], string='Источник энергии', default='grid')
    power_kw = fields.Integer(string='Мощность, кВт')
    monthly_kwh = fields.Integer(string='Потребление, кВт·ч в месяц')
    hashrate = fields.Float(string='Хешрейт, TH/s', digits=(16, 1))
    equipment = fields.Text(string='Оборудование')
    coins = fields.Char(string='Что добывает', default='BTC')
    restricted_region = fields.Boolean(
        string='Регион в перечне ограничений',
        help='Правительство ограничивает майнинг в ряде регионов, перечень '
             'меняется по сезонам. Отметку ставит сам майнер.')
    over_limit = fields.Boolean(compute='_compute_over_limit', store=True)
    warning_html = fields.Html(compute='_compute_warning', sanitize=False)
    offer_ids = fields.One2many('coop.mining.offer', 'miner_id', string='Предложения')
    offer_count = fields.Integer(compute='_compute_offer_count')

    _one_per_partner = models.Constraint('unique(partner_id)',
                                         'У участника уже есть карточка майнера.')

    @api.depends('kind', 'monthly_kwh')
    def _compute_over_limit(self):
        for miner in self:
            miner.over_limit = miner.kind == 'person' and (miner.monthly_kwh or 0) > PERSON_KWH_LIMIT

    def _compute_warning(self):
        for miner in self:
            parts = [Markup('<div class="alert alert-info mb-2">%s</div>') % NOTICE]
            if miner.over_limit:
                parts.append(Markup('<div class="alert alert-warning mb-2">%s</div>') % _(
                    'Потребление выше лимита для физлица без ИП: нужна регистрация '
                    'ИП или юрлица и запись в реестре ФНС.'))
            if miner.kind in ('legal', 'ip') and miner.registry_state in ('missing', 'not_required'):
                parts.append(Markup('<div class="alert alert-warning mb-2">%s</div>') % _(
                    'Юрлицо и ИП майнят только после включения в реестр ФНС.'))
            if miner.restricted_region:
                parts.append(Markup('<div class="alert alert-warning mb-2">%s</div>') % _(
                    'Регион в перечне ограничений: майнинг там сейчас запрещён.'))
            miner.warning_html = Markup('').join(parts)

    def _compute_offer_count(self):
        for miner in self:
            miner.offer_count = len(miner.offer_ids)

    @api.constrains('kind', 'registry_state', 'monthly_kwh')
    def _check_registry(self):
        for miner in self:
            if miner.registry_state != 'not_required':
                continue
            if miner.kind in ('legal', 'ip'):
                raise ValidationError(_(
                    'Юрлицу и ИП запись в реестре ФНС нужна всегда.'))
            if (miner.monthly_kwh or 0) > PERSON_KWH_LIMIT:
                raise ValidationError(_(
                    'Сверх %(limit)s кВт·ч в месяц физлицу без записи нельзя: нужен '
                    'ИП или юрлицо и реестр ФНС.', limit=PERSON_KWH_LIMIT))

    def _coop_catalog_filters(self, domain):
        def choice(name):
            return [{'value': code, 'label': label}
                    for code, label in self._fields[name].selection]
        return [
            {'code': 'kind', 'label': 'Кто по форме', 'widget': 'select', 'field': 'kind',
             'placeholder': 'Любой', 'options': choice('kind')},
            {'code': 'registry', 'label': 'Реестр ФНС', 'widget': 'select',
             'field': 'registry_state', 'placeholder': 'Любой', 'options': choice('registry_state')},
            {'code': 'energy', 'label': 'Источник энергии', 'widget': 'select',
             'field': 'energy_source', 'placeholder': 'Любой', 'options': choice('energy_source')},
            {'code': 'city', 'label': 'Город', 'widget': 'text', 'field': 'city',
             'operator': 'ilike', 'placeholder': 'Начните вводить город'},
            {'code': 'power', 'label': 'Мощность, кВт', 'widget': 'range', 'field': 'power_kw'},
        ]


class CoopMiningOffer(models.Model):
    """Предложение на бирже майнинговых мощностей.

    Аренда места и электроэнергии, аренда оборудования, аренда хешрейта
    и сервис — обычные услуги, статуса не требуют (разбор, 2.4). Продажа
    намайненного здесь не выставляется: это обмен, у него свой раздел.
    """
    _name = 'coop.mining.offer'
    _description = 'Предложение майнинговых мощностей'
    _inherit = ['mail.thread']
    _order = 'published_on desc, id desc'

    name = fields.Char(string='Заголовок', required=True)
    side = fields.Selection([('offer', 'Предлагаю'), ('request', 'Ищу')],
                            string='Сторона', required=True, default='offer', index=True)
    kind = fields.Selection([
        ('hosting', 'Размещение оборудования'),
        ('equipment', 'Аренда оборудования'),
        ('hashrate', 'Аренда хешрейта'),
        ('service', 'Ремонт и обслуживание'),
    ], string='Что', required=True, default='hosting', index=True)
    miner_id = fields.Many2one('coop.miner', string='Майнер', index=True)
    author_id = fields.Many2one('res.partner', string='Кто', required=True, index=True,
                                default=lambda self: self.env.user.partner_id)
    city = fields.Char(string='Город', index=True)
    energy_source = fields.Selection(related='miner_id.energy_source', store=True)
    capacity = fields.Integer(string='Объём')
    capacity_unit = fields.Selection([
        ('kw', 'кВт'), ('places', 'мест'), ('devices', 'устройств'), ('ths', 'TH/s'),
    ], string='Единица', default='kw')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.ref('base.RUB', raise_if_not_found=False))
    price = fields.Monetary(string='Цена, ₽')
    price_unit = fields.Selection([
        ('kwh', 'за кВт·ч'), ('device_month', 'за устройство в месяц'),
        ('ths_day', 'за TH/s в сутки'), ('hour', 'за час работы'),
    ], string='За что', default='kwh')
    min_term = fields.Char(string='Минимальный срок')
    infra_registered = fields.Boolean(
        string='В реестре операторов инфраструктуры',
        help='Предоставление майнинговых мощностей — отдельный реестр ФНС.')
    description = fields.Text(string='Подробности')
    state = fields.Selection([('published', 'Опубликовано'), ('closed', 'Снято')],
                             string='Состояние', default='published', required=True, index=True)
    published_on = fields.Datetime(string='Опубликовано', default=fields.Datetime.now, index=True)
    price_label = fields.Char(compute='_compute_labels')
    capacity_label = fields.Char(compute='_compute_labels')
    icon = fields.Char(compute='_compute_labels')
    is_mine = fields.Boolean(compute='_compute_is_mine', search='_search_is_mine')

    def _compute_labels(self):
        units = dict(self._fields['price_unit'].selection)
        cap_units = dict(self._fields['capacity_unit'].selection)
        icons = {'hosting': '🏭', 'equipment': '🖥', 'hashrate': '⚡', 'service': '🛠'}
        for offer in self:
            offer.price_label = ('{:,.2f} ₽ {}'.format(offer.price, units.get(offer.price_unit, ''))
                                 .replace(',', ' ').replace('.', ',')) if offer.price else 'Договорная'
            offer.capacity_label = ('%s %s' % ('{:,}'.format(offer.capacity).replace(',', ' '),
                                               cap_units.get(offer.capacity_unit, ''))
                                    if offer.capacity else '')
            offer.icon = icons.get(offer.kind, '⛏')

    def _compute_is_mine(self):
        me = self.env.user.partner_id
        for offer in self:
            offer.is_mine = offer.author_id == me

    def _search_is_mine(self, operator, value):
        positive = (operator == '=') == bool(value)
        return [('author_id', '=' if positive else '!=', self.env.user.partner_id.id)]

    def action_close(self):
        self.write({'state': 'closed'})

    def action_publish(self):
        self.write({'state': 'published'})

    def _coop_catalog_filters(self, domain):
        def choice(name):
            return [{'value': code, 'label': label}
                    for code, label in self._fields[name].selection]
        return [
            {'code': 'side', 'label': 'Предлагают или ищут', 'widget': 'select', 'field': 'side',
             'placeholder': 'Любое', 'options': choice('side')},
            {'code': 'kind', 'label': 'Что', 'widget': 'select', 'field': 'kind',
             'placeholder': 'Любое', 'options': choice('kind')},
            {'code': 'energy', 'label': 'Источник энергии', 'widget': 'select',
             'field': 'energy_source', 'placeholder': 'Любой', 'options': [
                 {'value': code, 'label': label}
                 for code, label in self.env['coop.miner']._fields['energy_source'].selection]},
            {'code': 'city', 'label': 'Город', 'widget': 'text', 'field': 'city',
             'operator': 'ilike', 'placeholder': 'Начните вводить город'},
            {'code': 'price', 'label': 'Цена, ₽', 'widget': 'range', 'field': 'price'},
            {'code': 'quick', 'label': 'Быстрые фильтры', 'widget': 'quick', 'options': [
                {'value': 'infra', 'label': '🏛 В реестре операторов',
                 'domain': [('infra_registered', '=', True)]},
                {'value': 'hydro', 'label': '💧 ГЭС', 'domain': [('energy_source', '=', 'hydro')]},
            ]},
        ]
