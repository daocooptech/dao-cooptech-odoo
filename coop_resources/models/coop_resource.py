# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Сколько объявлений на странице каталога. От этого зависит, какой
# сквозной номер получает «строка 3 страницы 5», поэтому число одно и то
# же в модели и в действии, а не подобрано на глаз в каждом месте.
PAGE_SIZE = 20


class CoopResourceCategory(models.Model):
    """Товарная категория ресурса.

    Дерево своё, а не общий справочник специализаций, и это не
    непоследовательность. У людей, организаций, вакансий и навыков
    справочник отвечает на вопрос «кто это и что умеет», а здесь — «что
    это за вещь»: Недвижимость, Транспорт, Электроника, Продовольственные
    товары. Свести «Сварщика» и «Ноутбуки и компьютеры» в один справочник
    значит получить список, в котором ничего не найти.
    """
    _name = 'coop.resource.category'
    _description = 'Категория ресурсов'
    _parent_store = True
    _order = 'complete_name'

    name = fields.Char(string='Название', required=True)
    parent_id = fields.Many2one(
        'coop.resource.category', string='Родительская категория',
        ondelete='restrict', index=True)
    parent_path = fields.Char(index=True, unaccent=False)
    child_ids = fields.One2many(
        'coop.resource.category', 'parent_id', string='Подкатегории')
    complete_name = fields.Char(
        string='Полное название', compute='_compute_complete_name',
        recursive=True, store=True)
    resource_count = fields.Integer(
        string='Ресурсов', compute='_compute_resource_count')

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for record in self:
            if record.parent_id:
                record.complete_name = '%s / %s' % (
                    record.parent_id.complete_name, record.name)
            else:
                record.complete_name = record.name

    def _compute_resource_count(self):
        counts = {
            category.id: total
            for category, total in self.env['coop.resource']._read_group(
                [('category_id', 'in', self.ids)],
                groupby=['category_id'], aggregates=['__count'])
        } if self.ids else {}
        for record in self:
            record.resource_count = counts.get(record.id, 0)


class CoopResourceMethod(models.Model):
    """Способ передачи ресурса.

    Справочник, а не перечисление в коде: способов уже семь, и от каждого
    зависят разные правила. У продажи есть цена и переход права
    собственности, у аренды — срок возврата, у участия в проекте — доля,
    считаемая от денежной оценки вклада. Держать это в коде значит менять
    код всякий раз, когда появится новый способ договориться.
    """
    _name = 'coop.resource.method'
    _description = 'Способ передачи'
    _order = 'sequence, name'

    name = fields.Char(string='Название', required=True)
    code = fields.Char(string='Код', required=True)
    sequence = fields.Integer(string='Порядок', default=10)
    requires_price = fields.Boolean(
        string='Требует денежной оценки', default=False,
        help='У продажи и участия в проекте оценка обязательна: без неё '
             'нечего платить и не от чего считать долю. У обмена и '
             'безвозмездной передачи она может пустовать.')
    is_monetary = fields.Boolean(
        string='Денежный расчёт', default=False,
        help='Расчёт происходит деньгами. Снято у обмена, безвозмездной '
             'передачи и участия в проекте.')

    _code_uniq = models.Constraint(
        'unique(code)',
        'Такой способ передачи уже есть.',
    )


class CoopResource(models.Model):
    """Ресурс платформы — предложение или запрос.

    Собственная модель, а не товар Odoo (решение владельца от 2026-09-01).
    На product.template сразу заработали бы склад, продажи и закупки, но
    половина каталога — это «ищу» и «отдам даром», а товар по определению
    то, что продают. Натягивать спрос на товар значит завести поле «это на
    самом деле не товар» и всюду его проверять.

    Плата за это решение известна заранее: связь со складом и со сделками
    придётся заводить руками, когда до них дойдёт очередь.
    """
    _name = 'coop.resource'
    _description = 'Ресурс'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    # Порядок в каталоге считается заранее и хранится числом: платное
    # объявление стоит не «выше всех», а на конкретной строке конкретной
    # страницы, и выразить это одним сравнением полей нельзя. Как
    # считается — см. _recompute_catalog_rank.
    _order = 'catalog_rank, id desc'

    name = fields.Char(string='Название', required=True, tracking=True)
    description = fields.Html(string='Описание')
    image_1920 = fields.Image(string='Фотография', max_width=1920, max_height=1920)
    image_512 = fields.Image(related='image_1920', max_width=512, max_height=512, store=True)

    listing_type = fields.Selection([
        ('offer', 'Предложение'),
        ('request', 'Спрос'),
    ], string='Вид объявления', required=True, default='offer',
        tracking=True, index=True,
        help='Предложение — «отдам, продам, сдам». Спрос — «ищу, куплю, '
             'приму в дар».')

    resource_type = fields.Selection([
        ('material', 'Материальный'),
        ('equipment', 'Оборудование'),
        ('financial', 'Финансовый'),
        ('labour', 'Труд'),
    ], string='Тип ресурса', required=True, default='material', index=True)

    category_id = fields.Many2one(
        'coop.resource.category', string='Категория',
        ondelete='restrict', index=True)
    method_ids = fields.Many2many(
        'coop.resource.method', string='Способы передачи',
        help='Как владелец готов расстаться с ресурсом: продать, обменять, '
             'отдать даром, внести в проект.')

    owner_id = fields.Many2one(
        'res.partner', string='Владелец', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(), tracking=True,
        help='Человек или организация. Обе стороны сделки равноправны, '
             'поэтому владельцем может быть и то и другое.')
    author_id = fields.Many2one(
        'res.partner', string='Разместил', readonly=True,
        default=lambda self: self.env.user.partner_id, index=True,
        help='Кто из людей это разместил. У объявления частного лица '
             'совпадает с владельцем; у объявления организации '
             'показывает, кто из её представителей нажал кнопку — без '
             'этого спор «кто это разместил» разбирать нечем.')
    city = fields.Char(string='Город', index=True)

    # ── Цена ─────────────────────────────────────────────────────────────
    #
    # Хранится рублёвая оценка, даже когда расчёта деньгами нет. Она нужна
    # не для продажи: доля участника в проекте считается от денежной
    # оценки вклада, и без неё вклад ресурсом посчитать не от чего.
    price = fields.Monetary(string='Цена или оценка', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)
    price_kind = fields.Selection([
        ('from', 'от'),
        ('to', 'до'),
        ('exact', 'ровно'),
        ('none', 'по договорённости'),
    ], string='Уточнение цены', default='from', required=True)
    price_unit_label = fields.Char(
        string='За единицу',
        help='Как в объявлении: кг, тонна, шт., сутки, м². Свободный текст, '
             'потому что единицы у ресурсов несопоставимы: сравнивать '
             '«за сутки» и «за м³» всё равно бессмысленно.')
    price_display = fields.Char(
        string='Цена строкой', compute='_compute_price_display', store=True)

    # ── Продвижение ──────────────────────────────────────────────────────
    promoted_until = fields.Datetime(
        string='Продвигается до', readonly=True, tracking=True,
        help='Пока дата не прошла, объявление показывается выше остальных.')
    is_promoted = fields.Boolean(
        string='Продвигается', compute='_compute_is_promoted', search='_search_is_promoted')
    promotion_slot_id = fields.Many2one(
        'coop.promotion.slot', string='Место в выдаче', readonly=True,
        help='Страница и строка, на которых показывается объявление, пока '
             'оплачен срок.')
    catalog_rank = fields.Integer(
        string='Место в каталоге', index=True, readonly=True, default=0,
        help='Служебное поле: порядковый номер объявления в общей выдаче. '
             'Пересчитывается при изменении продвижения.')

    # Когда владелец в последний раз подтвердил, что объявление ещё
    # актуально. Отдельно от даты создания: объявление живёт годами, а
    # спрашивают о нём раз в месяц, и после подтверждения отсчёт должен
    # начинаться заново. По этой отметке «Моя страница» решает, о чём
    # напомнить владельцу.
    refreshed_on = fields.Datetime(
        string='Подтверждено владельцем', default=fields.Datetime.now,
        help='Дата последнего подтверждения, что объявление актуально.')

    state = fields.Selection([
        ('draft', 'Черновик'),
        ('published', 'Опубликовано'),
        ('closed', 'Закрыто'),
    ], string='Состояние', default='published', required=True, tracking=True, index=True)

    @api.depends('price', 'price_kind', 'price_unit_label', 'currency_id')
    def _compute_price_display(self):
        prefix = {'from': 'от ', 'to': 'до ', 'exact': '', 'none': ''}
        for record in self:
            if record.price_kind == 'none' or not record.price:
                record.price_display = 'по договорённости'
                continue
            amount = '{:,.0f}'.format(record.price).replace(',', ' ')
            symbol = record.currency_id.symbol or '₽'
            unit = '/%s' % record.price_unit_label if record.price_unit_label else ''
            record.price_display = '%s%s %s%s' % (
                prefix.get(record.price_kind, ''), amount, symbol, unit)

    @api.depends('promoted_until', 'promotion_slot_id')
    def _compute_is_promoted(self):
        now = fields.Datetime.now()
        for record in self:
            record.is_promoted = bool(
                record.promotion_slot_id
                and record.promoted_until and record.promoted_until > now)

    def _search_is_promoted(self, operator, value):
        now = fields.Datetime.now()
        promoted = [('promoted_until', '>', now)]
        not_promoted = ['|', ('promoted_until', '=', False), ('promoted_until', '<=', now)]
        if operator not in ('=', '!='):
            raise UserError(_('По этому признаку можно искать только равенством.'))
        positive = (operator == '=') == bool(value)
        return promoted if positive else not_promoted

    @api.constrains('method_ids', 'price', 'price_kind')
    def _check_price_required(self):
        """Оценка обязательна там, где без неё нельзя посчитать.

        Продажа без цены — это не объявление, а вопрос; вклад в проект без
        оценки не даёт посчитать долю. У обмена и безвозмездной передачи
        оценка может пустовать: там договариваются о вещи, а не о сумме.
        """
        for record in self:
            if record.price or record.price_kind == 'none':
                continue
            requiring = record.method_ids.filtered('requires_price')
            if requiring:
                raise UserError(_(
                    'Для способа «%(method)s» нужна цена или оценка: без неё '
                    'нечего платить и не от чего считать долю в проекте.',
                    method=requiring[0].name))

    @api.model
    def _cron_expire_promotions(self):
        """Освободить места, срок показа на которых истёк.

        Место освобождается, а дата остаётся: по ней видно, что
        объявление продвигалось и когда. Без этого задания истёкшее
        продвижение держало бы место занятым вечно, и купить его никто бы
        не смог.
        """
        expired = self.search([
            ('promotion_slot_id', '!=', False),
            ('promoted_until', '<=', fields.Datetime.now()),
        ])
        if expired:
            expired.write({'promotion_slot_id': False})
            _logger.info('Продвижение истекло у %s объявлений', len(expired))
        self._recompute_catalog_rank()
        return True

    @api.model
    def _recompute_catalog_rank(self):
        """Разложить каталог по местам: платные — на свои, остальные — между.

        Считается целиком и заранее, потому что выразить это порядком по
        полям нельзя. Объявление, купившее третью строку пятой страницы,
        должно стоять именно там: не выше — иначе платное место теряет
        смысл, и не ниже — иначе его обманули. Значит нужен сквозной
        номер по всему каталогу, а он зависит от того, какие места
        выкуплены прямо сейчас.

        Обычные объявления заполняют оставшиеся номера в своём порядке —
        по свежести. Пересчёт идёт по опубликованным: черновики и
        закрытые в выдаче не участвуют.
        """
        now = fields.Datetime.now()
        promoted = self.search([
            ('state', '=', 'published'),
            ('promotion_slot_id', '!=', False),
            ('promoted_until', '>', now),
        ])

        page_size = int(self.env['ir.config_parameter'].sudo().get_param(
            'coop_resources.page_size', PAGE_SIZE))

        taken = {}
        for record in promoted:
            slot = record.promotion_slot_id
            index = (slot.page - 1) * page_size + slot.position
            # Если два объявления претендуют на одно место — а такого не
            # должно быть, — побеждает то, чей срок кончается позже.
            current = taken.get(index)
            if not current or (record.promoted_until or now) > (current.promoted_until or now):
                taken[index] = record

        rest = self.search([('state', '=', 'published')],
                           order='create_date desc, id desc') - promoted

        values = {record.id: index for index, record in taken.items()}
        cursor = 1
        for record in rest:
            while cursor in taken:
                cursor += 1
            values[record.id] = cursor
            cursor += 1

        # Записываем только изменившееся: каталог пересчитывается при
        # каждой покупке места, и переписывать две сотни строк целиком
        # незачем.
        for record in promoted | rest:
            rank = values.get(record.id, 0)
            if record.catalog_rank != rank:
                record.catalog_rank = rank
        return True

    def action_publish(self):
        """Опубликовать объявление о ресурсе.

        Нужна подтверждённая ступень контакта — телефон. Ниже неё
        участник только смотрит.
        """
        for record in self:
            record.owner_id.coop_require_level(
                'contact', _('опубликовать объявление'))
        self.write({'state': 'published'})
        return True

    def action_close(self):
        self.write({'state': 'closed'})
        return True


class CoopResourceCatalogFilters(models.Model):
    """Панель фильтров каталога ресурсов — та же, что в макете.

    Порядок полей и подписи взяты оттуда же: быстрые фильтры, вид
    объявления, рубрика, город, цена, тип, способ получения.
    """

    _inherit = 'coop.resource'

    def _coop_catalog_filters(self, domain):
        methods = self.env['coop.resource.method'].sudo().search([])
        exchange = methods.filtered(lambda m: 'бмен' in m.name)
        free = methods.filtered(lambda m: 'езвозмезд' in m.name)

        categories = self.env['coop.resource.category'].sudo().search(
            [], order='complete_name')

        quick = []
        # Значки в подписях — из макета: чипы стоят в ряд, и по значку
        # нужный находится быстрее, чем по прочтении трёх подписей.
        if exchange:
            quick.append({'value': 'exchange', 'label': '🔄 На обмен',
                          'domain': [('method_ids', 'in', exchange.ids)]})
        if free:
            quick.append({'value': 'free', 'label': '🎁 Безвозмездно',
                          'domain': [('method_ids', 'in', free.ids)]})
        quick.insert(0, {'value': 'photo', 'label': '📷 С фото',
                         'domain': [('image_1920', '!=', False)]})

        # Быстрые фильтры стоят последними, перед кнопками: это ярлыки
        # к тому, что уже есть выше, и открывать ими панель значит
        # предлагать выбор до того, как человек понял, из чего выбирает.
        return [
            {'code': 'listing_type', 'label': 'Спрос или предложение',
             'hint': 'Предложение — «отдам, продам, сдам». '
                     'Спрос — «ищу, куплю, приму в дар».',
             'widget': 'select', 'field': 'listing_type', 'placeholder': 'Любая',
             'options': [{'value': code, 'label': label}
                         for code, label in
                         self._fields['listing_type'].selection]},
            {'code': 'category_id', 'label': 'Категория',
             'hint': 'Рубрика каталога. От неё зависят характеристики ниже.',
             'widget': 'select', 'field': 'category_id', 'placeholder': 'Любая',
             'options': [{'value': c.id, 'label': c.complete_name}
                         for c in categories]},
            {'code': 'city', 'label': 'Город',
             'hint': 'Можно ввести часть названия.',
             'widget': 'text', 'field': 'city', 'operator': 'ilike',
             'placeholder': 'Начните вводить город'},
            {'code': 'price', 'label': 'Цена, ₽',
             'hint': 'Пустое поле — без ограничения.',
             'widget': 'range', 'field': 'price'},
            {'code': 'resource_type', 'label': 'Тип',
             'hint': 'Материальный, оборудование, труд или финансовый.',
             'widget': 'select', 'field': 'resource_type', 'placeholder': 'Любой',
             'options': [{'value': code, 'label': label}
                         for code, label in
                         self._fields['resource_type'].selection]},
            {'code': 'method_ids', 'label': 'Способ получения',
             'hint': 'Продажа, аренда, обмен, безвозмездно и другие.',
             'widget': 'suggest', 'field': 'method_ids', 'operator': 'ilike',
             'placeholder': 'Например, аренда',
             'options': [{'value': m.id, 'label': m.name} for m in methods]},
            {'code': 'quick', 'label': 'Быстрые фильтры', 'widget': 'quick',
             'options': quick},
        ]
