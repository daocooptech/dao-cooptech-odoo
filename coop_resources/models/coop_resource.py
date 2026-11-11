# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.tools.safe_eval import safe_eval
from odoo.exceptions import UserError, ValidationError

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
    # Разделы — в порядке крупных площадок объявлений, а не по алфавиту и
    # не по числу записей: владелец 10–11.11.2026 — «наверху самые топовые
    # разделы, недвижимость, авто и т. д., как на Авито».
    _order = 'section_sequence, complete_name'

    name = fields.Char(string='Название', required=True)
    sequence = fields.Integer(
        string='Место на витрине', default=100,
        help='Чем меньше, тем выше раздел в каталоге и в выборе раздела. '
             'Задаётся у разделов верхнего уровня, подразделы идут за '
             'своим разделом.')
    section_sequence = fields.Integer(
        string='Место раздела', compute='_compute_section_sequence',
        recursive=True, store=True, index=True)
    parent_id = fields.Many2one(
        'coop.resource.category', string='Родительская категория',
        ondelete='restrict', index=True)
    parent_path = fields.Char(index=True)
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

    @api.depends('sequence', 'parent_id.section_sequence')
    def _compute_section_sequence(self):
        for record in self:
            record.section_sequence = (record.parent_id.section_sequence
                                       if record.parent_id else record.sequence)

    # Порядок разделов на главной Юлы 11.11.2026: «Недвижимость»,
    # «Легковые автомобили», «Услуги», дальше одежда, телефоны,
    # автотовары, вакансии, спецтехника (Авито с адреса стенда не открылся
    # — 429). Наши разделы шире, поэтому за ними — то, чего на досках
    # объявлений нет: оборудование, инструмент, сырьё и продовольствие.
    SECTION_RANKS = [
        'Недвижимость', 'Техника и транспорт', 'Услуги и финансы',
        'Электроника и оргтехника', 'Для дома и быта', 'Вещи и экипировка',
        'Оборудование и станки', 'Инструмент', 'Сырьё и материалы',
        'Продовольствие и сельхозпродукция',
    ]

    @api.model
    def _coop_rank_sections(self):
        """Места разделов — один раз: потом порядок правят руками в
        справочнике, и обновление модуля его не затирает."""
        Config = self.env['ir.config_parameter'].sudo()
        if Config.get_str('coop_resources.sections_ranked'):
            return True
        ranked = self.browse()
        for place, name in enumerate(self.SECTION_RANKS, start=1):
            section = self.search([('parent_id', '=', False), ('name', '=', name)])
            section.write({'sequence': place * 10})
            ranked |= section
        # Разделов ещё нет (чистая установка до наполнения) — признак не
        # ставим, иначе места не встанут и после наполнения.
        if ranked:
            Config.set_str('coop_resources.sections_ranked', '1')
        return True

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


# Имя, с которым заводится пустой черновик.
#
# Название у объявления обязательно на уровне базы, а черновик заводится
# до того, как человек что-нибудь напишет, — значит без заготовки его не
# создать. Заготовка одна и в коде одна: создание подставляет её, а
# публикация по ней же узнаёт, что название так и не заменили.
DRAFT_NAME = 'Новое объявление'


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
    _inherit = ['mail.thread', 'mail.activity.mixin', 'coop.page.mixin']
    # Форм у ресурса три: своя, проектная и токеномическая. Страницей
    # работает своя, поэтому вид назван явно.
    _coop_page_view = 'coop_resources.view_coop_resource_form'
    _coop_role_field = 'owner_id'
    _coop_role_text = 'Ваше объявление'
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
        help='Предложение — «отдам, продам, сдам». Спрос — «ищу, куплю».')

    # Подсказки «?» у полей — короткие, для человека (владелец 10.11.2026);
    # обоснования — здесь, в комментариях.
    #
    # Видов три (решение владельца 632 от 28.10.2026): материальные (сырьё,
    # оборудование, инструмент, техника, помещения, земля), трудовые и
    # финансовые. «Оборудование» влито в материальные: и то и другое —
    # вещь. Нематериальные (знания, программы, чертежи, ноу-хау, бренд) —
    # отдельным модулем coop_intangibles.
    resource_type = fields.Selection([
        ('material', 'Материальный'),
        ('financial', 'Финансовый'),
        ('labour', 'Труд'),
    ], string='Тип ресурса', required=True, default='material', index=True,
        help='Вещь, работа или деньги.')

    category_id = fields.Many2one(
        'coop.resource.category', string='Категория',
        ondelete='restrict', index=True)
    method_ids = fields.Many2many(
        'coop.resource.method', string='Способы передачи',
        help='Продать, обменять, отдать даром, внести в проект.')

    # ── Что именно предлагают ────────────────────────────────────────────
    #
    # Шесть полей из страницы размещения объявления в макете
    # (`add-resource.html`), которых в модели не было. Владелец 22
    # сентября 2026 на вопрос, добавлять ли их: «добавить все шесть».
    #
    # Все необязательные, и это не оплошность. Объявление бывает про
    # вещь, про услугу и про труд, и обязательное «состояние» у часа
    # работы электрика — это выдумка, которую человек вынужден заполнить
    # ложью. Обязательным остаётся только то, без чего объявление не
    # объявление: название, тип, категория, город.

    # У услуги, труда и денег — «не применимо»: там изнашивается не
    # предмет, а договорённость.
    condition = fields.Selection([
        ('new', 'Новое'),
        ('used', 'Б/у'),
        ('na', 'Не применимо'),
    ], string='Состояние', default='new',
        help='У труда и денег — «не применимо».')

    # Дробное: мерят не только штуками — полтонны, полтора часа.
    quantity = fields.Float(
        string='Количество', default=1.0,
        help='Сколько всего есть или нужно.')

    # Справочником не сделано намеренно: единицы у кооперативов свои
    # (рулон, ходка, смена), и список заставил бы выбирать неправильное.
    uom_label = fields.Char(
        string='Единица измерения',
        help='Своими словами: шт., кг, рулон, смена.')

    # Отдельным полем, а не припиской в описании: по нему фильтруют.
    bargain = fields.Boolean(
        string='Торг уместен',
        help='Готовы обсуждать цену.')

    # Пока строкой — общего реестра точек на платформе нет. Появится —
    # поле станет ссылкой на реестр, написанное останется подсказкой.
    pickup_point = fields.Char(
        string='Точка самовывоза',
        help='Адрес или ориентир.')

    # Платформа звонки не совершает; «только сообщения» — просьба не
    # звонить, а не техническое ограничение.
    contact_method = fields.Selection([
        ('both', 'Звонки и сообщения'),
        ('messages', 'Только сообщения'),
    ], string='Как связываться', default='both',
        help='Можно ли звонить владельцу.')

    owner_id = fields.Many2one(
        'res.partner', string='Владелец', required=True, index=True,
        default=lambda self: self.env.user._coop_publishing_partner(), tracking=True,
        help='Человек или организация.')
    author_id = fields.Many2one(
        'res.partner', string='Разместил', readonly=True,
        default=lambda self: self.env.user.partner_id, index=True,
        help='Кто из людей это разместил. У объявления частного лица '
             'совпадает с владельцем; у объявления организации '
             'показывает, кто из её представителей нажал кнопку — без '
             'этого спор «кто это разместил» разбирать нечем.')
    # По умолчанию — город того, от чьего имени размещают: объявление без
    # города выпадает из отбора по городу и стоит в каталоге без полосы с
    # городом на снимке (владелец 11.11.2026: «чёрная полоска с городом не
    # у всех»).
    city = fields.Char(
        string='Город', index=True,
        default=lambda self: self.env.user._coop_acting_partner().city or False)

    # ── Кто делает и из чего ─────────────────────────────────────────────
    #
    # Решение 370 от 22 сентября 2026. Владелец: «зависит всё от
    # количества модулей установленных у производителя… например если
    # стоит производственный модуль, то мы можем показывать
    # технологический и производственный процесс, состав, сотрудников
    # производивших конкретную партию».
    #
    # Отсюда главное для чтения этого куска: **карточка ресурса — не
    # фиксированный набор блоков, а витрина того, что участник
    # согласился показать из своих систем**. Пустой блок здесь не
    # недоделка, а честный ответ: у этого производителя такого учёта
    # нет. Поэтому ни одно из полей ниже не обязательное.

    manufacturer_ids = fields.Many2many(
        'res.partner', 'coop_resource_manufacturer_rel',
        'resource_id', 'partner_id', string='Производители',
        help='Кто это делает — их может быть несколько.')

    # Сырьё и оборудование — связями на такие же объявления, а не
    # текстом. Текстом «доска сосновая» — это слово; связью — живая
    # карточка с владельцем, ценой и городом, по которой видно, у кого
    # это взять. Ради этого различия связи и заводятся.
    material_ids = fields.Many2many(
        'coop.resource', 'coop_resource_material_rel',
        'resource_id', 'material_id', string='Сырьё',
        help='Из чего сделано — объявлениями о тех же ресурсах.')
    equipment_ids = fields.Many2many(
        'coop.resource', 'coop_resource_equipment_rel',
        'resource_id', 'equipment_id', string='Оборудование',
        help='На чём сделано.')

    # Сырьё и оборудование словами — решение владельца 26.10.2026, эталон
    # `ResourceAddPage` и `ResourcePage`. Связь с чужим объявлением
    # устаревает, когда его закрывают, а поиск по слову в своём городе
    # всегда показывает, где взять сейчас. Связи выше остаются для
    # заведённых раньше объявлений, новые пишутся словами.
    material_word_ids = fields.Many2many(
        'coop.resource.word', 'coop_resource_material_word_rel',
        'resource_id', 'word_id', string='Сырьё словами',
        help='Из чего сделано — словами: «Вощина», «Сахар».')
    equipment_word_ids = fields.Many2many(
        'coop.resource.word', 'coop_resource_equipment_word_rel',
        'resource_id', 'word_id', string='Оборудование словами',
        help='На чём сделано — словами: «Медогонка».')

    made_of_count = fields.Integer(
        string='Состав', compute='_compute_made_of_count')

    # Город смотрящего — в подсказке слова: «Найти «Вощина» в каталоге
    # ресурсов · Сочи». Тот же город подставляется в отбор каталога.
    coop_viewer_city = fields.Char(
        string='Город смотрящего', compute='_compute_coop_viewer_city')

    @api.depends_context('uid')
    def _compute_coop_viewer_city(self):
        city = self.env.user.partner_id.city or False
        for record in self:
            record.coop_viewer_city = city

    def action_find_word(self, word_id):
        """Слово состава → каталог ресурсов с поиском по слову в городе
        смотрящего (решение владельца 26.10.2026, эталон `ResourcePage`).

        Тот же экран «Каталог ресурсов», не отдельный: при поиске полок
        нет, лента карточек, все виды и отборы работают как обычно, а
        «назад» возвращает на ресурс хлебными крошками."""
        self.ensure_one()
        word = self.env['coop.resource.word'].browse(word_id).exists()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'coop_resources.action_coop_resources')
        # Контекст каталога (полки, подпись «Добавить ресурс») сохраняем —
        # иначе это был бы уже другой экран.
        context = dict(safe_eval(action.get('context') or '{}'),
                       search_default_name=word.name)
        if self.coop_viewer_city:
            context['search_default_city'] = self.coop_viewer_city
        action['context'] = context
        return action

    # ── Цена ─────────────────────────────────────────────────────────────
    #
    # Хранится рублёвая оценка, даже когда расчёта деньгами нет. Она нужна
    # не для продажи: доля участника в проекте считается от денежной
    # оценки вклада, и без неё вклад ресурсом посчитать не от чего.
    #
    # «В собственность / в пользование» — признак строки, а не вида
    # (решение владельца 632 от 28.10.2026): одна и та же вещь отдаётся
    # насовсем или на время, и от этого зависит и оценка вклада, и
    # возврат. Поэтому признак стоит у объявления и у потребности, а не
    # выводится из вида ресурса.
    ownership_kind = fields.Selection([
        ('property', 'В собственность'),
        ('use', 'В пользование'),
    ], string='Передаётся', default='property', required=True,
        help='Насовсем (продажа, дар) или на время (аренда, лизинг).')

    price = fields.Monetary(string='Цена или оценка', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.user._coop_acting_partner()._coop_currency())
    price_kind = fields.Selection([
        ('from', 'от'),
        ('to', 'до'),
        ('exact', 'ровно'),
        ('none', 'по договорённости'),
    ], string='Уточнение цены', default='exact', required=True,
        help='Обычно цена точная; «от» и «до» — редко.')
    # Свободный текст: единицы у ресурсов несопоставимы, сравнивать
    # «за сутки» и «за м³» всё равно бессмысленно.
    price_unit_label = fields.Char(
        string='За единицу',
        help='кг, шт., сутки, м²')
    price_display = fields.Char(
        string='Цена строкой', compute='_compute_price_display', store=True)

    # ── Продвижение ──────────────────────────────────────────────────────
    promoted_until = fields.Datetime(
        string='Продвигается до', readonly=True, tracking=True,
        help='До этой даты объявление выше остальных.')
    is_promoted = fields.Boolean(
        string='Продвигается', compute='_compute_is_promoted', search='_search_is_promoted')
    promotion_slot_id = fields.Many2one(
        'coop.promotion.slot', string='Место в выдаче', readonly=True,
        help='Где показывается, пока оплачен срок.')
    # Служебное: пересчитывается при изменении продвижения.
    catalog_rank = fields.Integer(
        string='Место в каталоге', index=True, readonly=True, default=0,
        help='Номер в общей выдаче.')

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

    # Кто стоит за объявлением — карточкой в боковой колонке витрины
    # (дизайн-система 25.10, `OwnerCard`, решение 625). Связанными
    # полями: форма показывает только поля своей модели, а человеку,
    # который решает, иметь ли дело, нужны знак, доверие и число сделок
    # владельца рядом с ценой, а не на чужой странице.
    owner_avatar = fields.Image(
        related='owner_id.avatar_128', string='Знак владельца')
    owner_trust = fields.Integer(
        related='owner_id.coop_trust', string='Доверие владельца, %')
    owner_deals_done = fields.Integer(
        related='owner_id.coop_deals_done', string='Сделок у владельца')
    owner_deals_reviewed = fields.Integer(
        related='owner_id.coop_deals_reviewed', string='Отзывов о владельце')
    # «Есть 120 кг» в строке фактов витрины. Строкой, а не самим числом:
    # дробное поле показывало «1,00» у штучного товара.
    quantity_display = fields.Char(
        string='Количество строкой', compute='_compute_quantity_display')

    @api.depends('quantity', 'uom_label')
    def _compute_quantity_display(self):
        for record in self:
            if not record.quantity:
                record.quantity_display = False
                continue
            number = ('%.3f' % record.quantity).rstrip('0').rstrip('.')
            whole, _dot, frac = number.partition('.')
            whole = '{:,}'.format(int(whole)).replace(',', ' ')
            number = whole + (',' + frac if frac else '')
            record.quantity_display = ' '.join(
                part for part in (number, record.uom_label) if part)

    def _coop_recompute_money_display(self):
        """Пересчитать хранимую строку суммы у всех записей.

        Строка хранится и считается от валюты записи, но валюту демо-набора
        меняли мимо ORM — и в каталоге стояло «от 4 500 $» при сумме в
        рублях на самой странице (сверка дизайна 20.10, решение 482).
        Зовётся из `data/coop_money_display.xml` при каждом обновлении
        модуля: дёшево и ничего не портит при повторе.
        """
        records = self.sudo().with_context(active_test=False).search([])
        self.env.add_to_compute(self._fields['price_display'], records)
        records.flush_recordset(['price_display'])

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
        # Odoo 19 ищет признак оператором `in` ([True]); «не продвигается»
        # движок выводит сам из NotImplemented.
        if operator != 'in':
            return NotImplemented
        return promoted

    @api.model
    def action_new_listing(self):
        """Завести черновик объявления и открыть страницу размещения.

        Почему запись создаётся сразу, а не по кнопке «Сохранить».
        Владелец 22 сентября 2026 выбрал из трёх устройств страницы
        «одной страницей, но с автосохранением черновика». Автосохранение
        на платформе уже есть и работает так: каждое поле сохраняет себя
        само, по галочке (решение 344). Но сохранять себя поле может
        только в существующую запись — значит запись должна появиться до
        того, как человек начнёт писать, а не после.

        Отсюда черновик: он заводится пустым при нажатии «Добавить»,
        и дальше человек его наполняет. Ушёл со страницы на полпути —
        написанное осталось, и объявление ждёт в черновиках, а не пропало.

        Пустой черновик, брошенный сразу, — цена этого решения. Он ничей
        и никому не виден: черновики в каталог не выходят. Чистка старых
        пустых черновиков — отдельная работа, пока её нет.
        """
        draft = self.create({'state': 'draft', 'name': DRAFT_NAME})
        action = self.env['ir.actions.act_window']._for_xml_id(
            'coop_resources.action_coop_resource_add')
        action['res_id'] = draft.id
        return action

    def action_edit_listing(self):
        """Открыть своё объявление страницей размещения — править.

        Витрина показывает объявление, а не форму: пустые блоки на ней
        скрыты (владелец 27.10.2026), и дописать состав или условия там
        негде. Правка — той же страницей, что и размещение."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'coop_resources.action_coop_resource_add')
        action['res_id'] = self.id
        return action

    def action_save_draft(self):
        """«Сохранить черновик»: запись уже сохранена кнопкой — уходим к
        своим объявлениям, где черновик и ждёт."""
        action = self.env['ir.actions.act_window']._for_xml_id(
            'coop_resources.action_coop_my_resources')
        action['target'] = 'main'
        return action

    def action_done_editing(self):
        """«Готово» у опубликованного: обратно на витрину объявления."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'coop.resource',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('coop_resources.view_coop_resource_form').id, 'form')],
            # `main` — путь начинается заново: иначе в крошках копится
            # «объявление → правка → объявление».
            'target': 'main',
        }

    @api.depends('material_ids', 'equipment_ids',
                 'material_word_ids', 'equipment_word_ids')
    def _compute_made_of_count(self):
        for record in self:
            record.made_of_count = (
                len(record.material_ids) + len(record.equipment_ids)
                + len(record.material_word_ids) + len(record.equipment_word_ids))

    @api.constrains('material_ids', 'equipment_ids')
    def _check_not_made_of_itself(self):
        """Ресурс не может быть сделан из самого себя.

        Прямое кольцо проверяем обязательно: «доска сделана из доски» —
        это не рекурсия материалов, а опечатка, и она портит и вид, и
        любой обход состава.

        Кольца длиннее двух звеньев не ловим намеренно. Состав ресурса —
        не дерево счетов: «мука из зерна, зерно с поля, на поле трактор,
        трактор из стали, сталь на печи, печь из кирпича» — цепочка
        может честно замкнуться через десяток звеньев в настоящем
        производстве, и запрещать это значило бы решать за участника,
        как устроено его дело.
        """
        for record in self:
            if record in record.material_ids | record.equipment_ids:
                raise ValidationError(_(
                    'Ресурс не может быть сделан из самого себя.'))

    @api.constrains('method_ids', 'price', 'price_kind', 'term_ids')
    def _check_price_required(self):
        """Оценка обязательна там, где без неё нельзя посчитать.

        Продажа без цены — это не объявление, а вопрос; вклад в проект без
        оценки не даёт посчитать долю. У обмена и безвозмездной передачи
        оценка может пустовать: там договариваются о вещи, а не о сумме.
        """
        for record in self:
            # Цена во вкладке способа — тоже цена: на карточку она попадёт
            # следом (`_coop_price_from_terms`), а проверка идёт раньше.
            if (record.price or record.price_kind == 'none'
                    or any(t.price or t.price_kind == 'none' for t in record.term_ids)):
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

        page_size = int(self.env['ir.config_parameter'].sudo().get_str('coop_resources.page_size') or PAGE_SIZE)

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

    # ── Отклик участника ─────────────────────────────────────────────
    #
    # Каталог ресурсов — самый большой на платформе, а действий у него
    # было три, и все три владельца объявления: опубликовать, закрыть,
    # продвинуть. Тому, кто нашёл нужное, нажать было нечего.

    can_respond = fields.Boolean(
        string='Можно откликнуться', compute='_compute_can_respond',
        help='Объявление опубликовано, и оно не моё.')
    # Подпись кнопки — по способу передачи, а не одна на всё.
    #
    # Сначала здесь стояло «Откликнуться» — слово, которого в макете нет
    # вовсе. Владелец остановил: «что ты делаешь, какие еще отклики в
    # ресурсах?» В макете (`resource.html`) язык раздела торговый:
    # «Купить в один клик», «Добавить в корзину», «Написать владельцу».
    #
    # Но «купить» годится не всякому объявлению: у аренды берут напрокат,
    # даром — принимают, на обмен — предлагают своё, а у объявления о
    # спросе покупает как раз разместивший. Одна подпись на все случаи
    # обещала бы не то, что произойдёт.
    respond_label = fields.Char(
        string='Подпись кнопки', compute='_compute_respond_label')

    @api.depends('listing_type', 'method_ids')
    def _compute_respond_label(self):
        for record in self:
            if record.listing_type == 'request':
                # Спрос: разместивший ищет, откликнувшийся отдаёт.
                record.respond_label = 'Предложить своё'
                continue
            codes = set(record.method_ids.mapped('code'))
            if 'free' in codes and not (codes - {'free'}):
                record.respond_label = 'Принять в дар'
            elif 'barter' in codes and not (codes - {'barter'}):
                record.respond_label = 'Предложить обмен'
            elif codes and not (codes - {'rent', 'leasing'}):
                record.respond_label = 'Арендовать'
            else:
                record.respond_label = 'Купить в один клик'

    def action_message_owner(self):
        """Написать владельцу объявления.

        В макете это отдельная кнопка рядом с покупкой: спросить о
        подробностях, не заводя сделку. Ведёт в сообщения, как и «Написать»
        на карточке человека и организации, — переписка на платформе одна.
        """
        self.ensure_one()
        if not self.owner_id:
            raise UserError(_('У объявления не указан владелец.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Написать: %s') % self.owner_id.display_name,
            'res_model': 'discuss.channel',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_channel_partner_ids': [(4, self.owner_id.id)]},
        }

    # «Показать номер» в карточке владельца (эталон `OwnerCard`, владелец
    # 10.11.2026). Номер не лежит в данных витрины — приходит по нажатию:
    # так его не соберёт тот, кто просто листает объявления. При «Только
    # сообщения» кнопки нет — это просьба не звонить.
    owner_has_phone = fields.Boolean(
        string='Можно показать номер', compute='_compute_owner_has_phone')

    @api.depends('owner_id', 'contact_method')
    def _compute_owner_has_phone(self):
        for record in self:
            owner = record.owner_id.sudo()
            record.owner_has_phone = bool(
                record.contact_method != 'messages' and owner.phone)

    def coop_owner_phone(self):
        """Номер владельца по нажатию «Показать номер»."""
        self.ensure_one()
        self.check_access('read')
        if not self.owner_has_phone:
            return False
        owner = self.owner_id.sudo()
        return owner.phone

    @api.depends_context('uid')
    @api.depends('state', 'owner_id')
    def _compute_can_respond(self):
        """Тот же вопрос, что решает кнопку, и тот же, что решает отказ.

        Разойдись они — и человек увидел бы кнопку, отвечающую ошибкой.
        """
        mine = self.env.user.coop_actor_partner_ids
        for record in self:
            record.can_respond = bool(
                record.state == 'published' and record.owner_id not in mine)

    # Подпись отклика по выбранному способу — переключатель на витрине
    # (дизайн-система, `ResourcePage`): подпись меняется вместе со
    # способом, и человек видит, что именно произойдёт по нажатию.
    RESPOND_LABELS = {
        'sale': 'Купить в один клик',
        'installment': 'Купить в рассрочку',
        'rent': 'Арендовать',
        'leasing': 'Взять в лизинг',
        'project': 'Позвать в проект',
        'barter': 'Предложить обмен',
        'free': 'Принять в дар',
    }

    def _coop_respond_label(self, method):
        self.ensure_one()
        if self.listing_type == 'request':
            return 'Предложить своё'
        return self.RESPOND_LABELS.get(method.code, self.respond_label)

    def action_respond(self):
        """Окно отклика: завести переговоры по сделке.

        Способ приходит с витрины (`coop_method_id` в контексте) — тот, что
        выбран переключателем; без него окно берёт первый способ."""
        self.ensure_one()
        method = self.env['coop.resource.method'].browse(
            self.env.context.get('coop_method_id')).exists() & self.method_ids
        term = self.term_ids.filtered(lambda t: t.method_id == method)[:1]
        context = {
            'default_resource_id': self.id,
            'default_amount': term.price or self.price,
        }
        if method:
            context['default_method_id'] = method.id
        label = self._coop_respond_label(method) if method else self.respond_label
        return {
            'type': 'ir.actions.act_window',
            'name': '%s: %s' % (label, self.name),
            'res_model': 'coop.resource.respond',
            'view_mode': 'form',
            'target': 'new',
            'context': context,
        }

    def action_publish(self):
        """Опубликовать объявление о ресурсе.

        Нужна подтверждённая ступень контакта — телефон. Ниже неё
        участник только смотрит.
        """
        for record in self:
            # Название так и не написали. Объявление «Новое объявление» в
            # каталоге бесполезно всем: его не найдут поиском, не поймут
            # в полке и не откроют. Отказ здесь дешевле, чем сто таких
            # строк в каталоге потом.
            if not record.name or record.name.strip() == DRAFT_NAME:
                raise UserError(_(
                    'Напишите, что вы размещаете. «%s» — это заготовка, '
                    'по ней объявление не найдут.') % DRAFT_NAME)
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

    def _coop_category_blocks(self, domain):
        """Рубрика цепочкой: раздел → подраздел → … (владелец 10.11.2026).

        Одним длинным списком «Недвижимость / Жилая / Квартиры» искать
        неудобно. Выбрал раздел — появился выбор подразделов, выбрал
        подраздел — появились его параметры (их добавляет `coop_attributes`
        для рубрики без вложенных). Каждое поле ветка: объявления её
        подразделов входят в отбор.
        """
        Category = self.env['coop.resource.category'].sudo()
        ids = [int(leaf[2]) for leaf in domain or []
               if isinstance(leaf, (list, tuple)) and len(leaf) == 3
               and leaf[0] == 'category_id' and leaf[1] in ('=', 'child_of')
               and isinstance(leaf[2], (int, str)) and str(leaf[2]).isdigit()]
        chosen = Category.browse(ids).exists()
        deepest = max(chosen, key=lambda c: (c.parent_path or '').count('/'),
                      default=Category)
        path = []
        node = deepest
        while node:
            path.insert(0, node)
            node = node.parent_id
        # Числа у вариантов считаются по остальным условиям, без выбора
        # рубрики: иначе у соседнего раздела всегда будет ноль.
        rest = [leaf for leaf in domain or []
                if not (isinstance(leaf, (list, tuple)) and len(leaf) == 3
                        and leaf[0] == 'category_id')]
        totals = {}
        for category, count in self._read_group(
                rest, ['category_id'], ['__count']):
            node = category
            while node:
                totals[node.id] = totals.get(node.id, 0) + count
                node = node.parent_id
        blocks = []
        for level, parent in enumerate([Category] + path):
            children = Category.search([('parent_id', '=', parent.id or False)])
            if not children:
                continue
            blocks.append({
                'code': 'category_l%d' % level,
                # Раздел, подраздел, а глубже — по имени родителя («Жилая»):
                # два поля «Подраздел» подряд не различить.
                'label': ('Раздел' if level == 0 else 'Подраздел'
                          if level == 1 else parent.name),
                'hint': 'Выберите раздел, затем подраздел: у каждого свои '
                        'параметры. В разделе — объявления всех его '
                        'подразделов.' if level == 0 else None,
                'widget': 'select', 'field': 'category_id',
                'operator': 'child_of', 'reload': True,
                'placeholder': 'Любой' if level == 0 else 'Любой подраздел',
                'options': [{'value': c.id, 'label': c.name,
                             'count': totals.get(c.id, 0)}
                            for c in children],
            })
        return blocks

    def _coop_catalog_filters(self, domain):
        methods = self.env['coop.resource.method'].sudo().search([])

        # «Быстрые фильтры» (с фото, на обмен, безвозмездно) убраны по
        # слову владельца 10.11.2026: «обмен» и «безвозмездно» уже есть
        # в «Способе получения», а отдельный ряд чипов только загромождал
        # панель.
        return [
            {'code': 'listing_type', 'label': 'Спрос или предложение',
             'hint': 'Предложение — «отдам, продам, сдам». '
                     'Спрос — «ищу, куплю, приму в дар».',
             'widget': 'select', 'field': 'listing_type', 'placeholder': 'Любая',
             'options': [{'value': code, 'label': label}
                         for code, label in
                         self._fields['listing_type'].selection]},
            *self._coop_category_blocks(domain),
            {'code': 'city', 'label': 'Город',
             'hint': 'Можно ввести часть названия.',
             'widget': 'text', 'field': 'city', 'operator': 'ilike',
             'placeholder': 'Начните вводить город'},
            {'code': 'price', 'label': 'Цена, ₽',
             'hint': 'Пустое поле — без ограничения.',
             'widget': 'range', 'field': 'price'},
            # Отбор по опту — чипом, а не полем: единственное «да/нет»
            # (решение 634, «только с оптовой ценой»).
            {'code': 'wholesale', 'label': 'Опт', 'widget': 'quick',
             'options': [{'value': 'wholesale', 'label': 'Только с оптовой ценой',
                          'domain': [('has_wholesale', '=', True)]}]},
            # «Тип» (материальный, финансовый, труд) убран из фильтра по
            # слову владельца 10.11.2026: разделы каталога уже разводят
            # их, а поле лишь дублировало выбор раздела.
            # Выпадающим списком, как раньше «Тип»: владелец 24 сентября 2026 —
            # «в каталоге ресурсов способ получения тоже выпадающий список
            # с вариантами». Способов десяток, и вводить их по памяти
            # незачем.
            {'code': 'method_ids', 'label': 'Способ получения',
             'hint': 'Продажа, аренда, обмен, безвозмездно и другие.',
             'widget': 'select', 'field': 'method_ids', 'operator': '=',
             'placeholder': 'Любой',
             'options': [{'value': m.id, 'label': m.name} for m in methods]},
        ]
