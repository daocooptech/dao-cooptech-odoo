# -*- coding: utf-8 -*-
"""Склад участника: сколько есть, сколько занято, сколько можно отдать.

Три числа, и они не равнозначны. Ёмкость — сколько склад вмещает вообще.
Занято под своё — то, чем владелец распоряжается сам. Сдано другим — то,
что уже отдано по договорённостям. Свободное считается вычитанием, и
только оно может попасть на биржу.

Считать свободное вручную нельзя: владелец введёт число один раз, потом
сдаст половину и забудет поправить, а на бирже останется предложение,
которого нет. Отсюда правило: сдано другим — вычисляемое поле по
действующим сделкам, а не то, что ввели руками.

Единица учёта у складов разная — квадратные метры, паллетоместа, тонны.
Приводить их к общей мере бессмысленно: паллетоместо в морозильнике и
квадратный метр открытой площадки различаются и ценой, и смыслом.
Поэтому сравнение идёт внутри одной единицы, а в сводке числа
складываются раздельно.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

STORAGE_KINDS = [
    ('dry_heated', 'Сухой отапливаемый'),
    ('dry_cold', 'Сухой неотапливаемый'),
    ('chilled', 'Холодильная камера, +2…+6 °C'),
    ('frozen', 'Морозильная камера, −18 °C'),
    ('open', 'Открытая площадка'),
]

CAPACITY_UNITS = [
    ('sqm', 'м²'),
    ('pallet', 'паллетоместа'),
    ('ton', 'тонны'),
]

# Условия, на которых место отдают. Список общий для зоны и предложения
# на бирже: участник не должен заново разбираться, что значит «пай»,
# переходя со своей карточки на чужую.
TERM_KINDS = [
    ('rent', 'Аренда'),
    ('custody', 'Ответственное хранение'),
    ('project', 'Участие в проекте'),
    ('buyout', 'Выкуп'),
    ('share', 'Пай (долевой выкуп)'),
    ('barter', 'Обмен мощностями'),
]

# Единица учёта склоняется по числу. «46 паллетоместа» — то, что
# получается из словаря названий, и то, на чём каталог перестаёт
# выглядеть написанным человеком. Квадратные метры не склоняются,
# поэтому правило нужно только двум единицам из трёх.
PLURALS = {
    'sqm': ('м²', 'м²', 'м²'),
    'pallet': ('паллетоместо', 'паллетоместа', 'паллетомест'),
    'ton': ('тонна', 'тонны', 'тонн'),
}


def unit_form(value, unit):
    """Название единицы в форме, которая подходит числу."""
    forms = PLURALS.get(unit)
    if not forms:
        return ''
    number = abs(int(round(value or 0)))
    if number % 10 == 1 and number % 100 != 11:
        return forms[0]
    if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
        return forms[1]
    return forms[2]


def amount_with_unit(value, unit):
    """Число и единица вместе: «46 паллетомест», «119 м²»."""
    return '%s %s' % (int(round(value or 0)), unit_form(value, unit))


class CoopWarehouse(models.Model):
    _name = 'coop.warehouse'
    _description = 'Склад'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'coop.page.mixin']
    _order = 'name'

    name = fields.Char(string='Название', required=True, tracking=True)
    active = fields.Boolean(default=True)

    owner_id = fields.Many2one(
        'res.partner', string='Владелец', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(),
        tracking=True)
    keeper_id = fields.Many2one(
        'res.partner', string='Ответственный за склад',
        help='К кому обращаться по приёмке и отгрузке. Не указан — значит '
             'к владельцу.')

    city = fields.Char(string='Город', index=True)
    address = fields.Char(string='Адрес')
    schedule = fields.Char(
        string='График работы', default='Пн–Пт, 9:00–18:00',
        help='Когда склад принимает и отдаёт. Круглосуточный склад — '
             'редкость, и об этом лучше сказать заранее.')

    storage_kind = fields.Selection(
        STORAGE_KINDS, string='Тип хранения', default='dry_heated',
        required=True, index=True, tracking=True)
    capacity_unit = fields.Selection(
        CAPACITY_UNITS, string='Единица учёта', default='sqm', required=True)

    capacity = fields.Float(
        string='Ёмкость', required=True, digits=(12, 1), tracking=True,
        help='Сколько склад вмещает всего, в выбранной единице учёта.')
    used_own = fields.Float(
        string='Занято под своё', digits=(12, 1),
        help='То, чем владелец распоряжается сам. На биржу не выходит.')
    used_rented = fields.Float(
        string='Сдано другим', digits=(12, 1), readonly=True,
        compute='_compute_used_rented', store=True,
        help='Считается по действующим договорённостям, руками не вводится: '
             'иначе на бирже остаётся место, которого уже нет.')
    free = fields.Float(
        string='Свободно', digits=(12, 1), compute='_compute_free', store=True)
    load_percent = fields.Integer(
        string='Занято, %', compute='_compute_free', store=True)

    # Доли для полосы занятости на карточке. Считаются здесь, а не в
    # шаблоне: шаблон канбана компилируется в JavaScript, и арифметика в
    # нём молча даёт `NaN` там, где в Python получилось бы число.
    own_percent = fields.Integer(compute='_compute_free', store=True)
    rented_percent = fields.Integer(compute='_compute_free', store=True)
    free_percent = fields.Integer(compute='_compute_free', store=True)
    unit_label = fields.Char(string='Единица', compute='_compute_free',
                             store=True)
    free_label = fields.Char(string='Свободно словами',
                             compute='_compute_free', store=True)
    capacity_label = fields.Char(string='Ёмкость словами',
                                 compute='_compute_free', store=True)
    own_label = fields.Char(string='Своё словами', compute='_compute_free',
                            store=True)
    rented_label = fields.Char(string='Сдано словами', compute='_compute_free',
                               store=True)

    zone_ids = fields.One2many('coop.warehouse.zone', 'warehouse_id',
                               string='Зоны')
    offer_ids = fields.One2many('coop.warehouse.offer', 'warehouse_id',
                                string='Предложения на бирже')
    offer_count = fields.Integer(string='Предложений',
                                 compute='_compute_counts')
    deal_ids = fields.One2many('coop.deal', 'warehouse_id',
                               string='Договорённости')
    deal_count = fields.Integer(string='Договорённостей',
                                compute='_compute_counts')

    resource_id = fields.Many2one(
        'coop.resource', string='Объявление в каталоге',
        help='Склад — такой же ресурс платформы, как техника или '
             'помещение. Здесь связь с объявлением, если оно заведено.')

    description = fields.Html(string='Описание')
    is_mine = fields.Boolean(string='Мой склад', compute='_compute_is_mine',
                             search='_search_is_mine')

    _capacity_positive = models.Constraint(
        'check(capacity > 0)',
        'Ёмкость склада должна быть больше нуля.',
    )

    # Место держат сделки, которые уже согласованы, но ещё не закрыты.
    # Состояния взяты из `coop.deal` дословно: состояния «подписана» там
    # нет — согласование называется `agreed`, приёмка `acceptance`, и на
    # приёмке место ещё занято: товар с него не вывезен.
    HOLDING_STATES = ('agreed', 'active', 'acceptance')

    @api.depends('deal_ids.state', 'deal_ids.warehouse_volume')
    def _compute_used_rented(self):
        for record in self:
            running = record.deal_ids.filtered(
                lambda deal: deal.state in record.HOLDING_STATES)
            record.used_rented = sum(running.mapped('warehouse_volume'))

    @api.depends('capacity', 'used_own', 'used_rented', 'capacity_unit')
    def _compute_free(self):
        units = dict(CAPACITY_UNITS)
        for record in self:
            free = record.capacity - record.used_own - record.used_rented
            record.free = max(free, 0.0)
            record.load_percent = (
                round((record.capacity - record.free) / record.capacity * 100)
                if record.capacity else 0)
            record.unit_label = units.get(record.capacity_unit, '')
            record.free_label = amount_with_unit(record.free,
                                                 record.capacity_unit)
            record.capacity_label = amount_with_unit(record.capacity,
                                                     record.capacity_unit)
            # В легенде под полосой единица не повторяется трижды: она
            # уже названа строкой выше, а «88,5» с дробной частью в
            # подписи из трёх слов читается как сбой счёта.
            record.own_label = '%s' % int(round(record.used_own or 0))
            record.rented_label = '%s' % int(round(record.used_rented or 0))
            if record.capacity:
                share = 100.0 / record.capacity
                record.own_percent = round((record.used_own or 0) * share)
                record.rented_percent = round((record.used_rented or 0) * share)
                # Свободное — остаток, а не третье независимое число:
                # три округления по отдельности дают полосу то в 99, то в
                # 101 процент, и у карточки дёргается правый край.
                record.free_percent = max(
                    0, 100 - record.own_percent - record.rented_percent)
            else:
                record.own_percent = 0
                record.rented_percent = 0
                record.free_percent = 0

    @api.depends('offer_ids.state', 'deal_ids')
    def _compute_counts(self):
        for record in self:
            record.offer_count = len(record.offer_ids.filtered(
                lambda offer: offer.state == 'published'))
            record.deal_count = len(record.deal_ids)

    @api.depends_context('uid')
    def _compute_is_mine(self):
        mine = self.env.user._coop_partner_ids()
        for record in self:
            record.is_mine = record.owner_id.id in mine

    def _search_is_mine(self, operator, value):
        # Odoo приводит `= True` к `in {True}` и передаёт множество, а не
        # список: значение разбирается как последовательность.
        if isinstance(value, (list, tuple, set, frozenset)):
            wanted = True in value
        else:
            wanted = bool(value)
        if operator in ('!=', 'not in'):
            wanted = not wanted
        mine = list(self.env.user._coop_partner_ids())
        return [('owner_id', 'in' if wanted else 'not in', mine)]

    @api.constrains('capacity', 'used_own', 'used_rented')
    def _check_capacity(self):
        for record in self:
            if record.used_own < 0:
                raise ValidationError(_(
                    'Занятое место не бывает отрицательным.'))
            if record.used_own + record.used_rented > record.capacity:
                raise ValidationError(_(
                    'Занято больше, чем вмещает склад: %(used)s из %(cap)s. '
                    'Либо ёмкость указана меньше настоящей, либо часть места '
                    'посчитана дважды.',
                    used=record.used_own + record.used_rented,
                    cap=record.capacity))

    def action_open_deals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Договорённости по складу'),
            'res_model': 'coop.deal',
            'view_mode': 'list,form',
            'domain': [('warehouse_id', '=', self.id)],
            'context': {'default_warehouse_id': self.id},
        }

    def action_publish_free(self):
        """Выставить свободное место на биржу.

        Отдельным действием, а не само собой при появлении свободного
        места: у склада бывает простой, который владелец держит нарочно —
        под свой же будущий урожай.
        """
        self.ensure_one()
        if self.free <= 0:
            raise UserError(_(
                'Свободного места нет: занято %(used)s из %(cap)s.',
                used=self.capacity - self.free, cap=self.capacity))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Выставить мощности на биржу'),
            'res_model': 'coop.warehouse.offer',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_warehouse_id': self.id,
                'default_volume': self.free,
            },
        }


class CoopWarehouseZone(models.Model):
    """Зона склада — часть, живущая по своим правилам.

    Зона нужна там, где склад неоднороден: у одной стены морозильник, у
    другой сухой стеллаж. Без зон владельцу приходится заводить два
    склада по одному адресу, и в каталоге они выглядят как два разных
    объекта в разных концах города.
    """
    _name = 'coop.warehouse.zone'
    _description = 'Зона склада'
    _order = 'warehouse_id, sequence, id'

    warehouse_id = fields.Many2one(
        'coop.warehouse', string='Склад', required=True, ondelete='cascade',
        index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Название', required=True)
    capacity = fields.Float(string='Ёмкость', digits=(12, 1))
    capacity_unit = fields.Selection(
        related='warehouse_id.capacity_unit', string='Единица')
    terms = fields.Selection(
        TERM_KINDS, string='На каких условиях',
        help='Пусто — зона под своё, на биржу не выходит.')
    note = fields.Char(string='Примечание')
