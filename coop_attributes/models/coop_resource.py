# -*- coding: utf-8 -*-
import logging
import re

from odoo import api, fields, models
from odoo.tools import SQL

# Имя индекса по значению характеристики. Общая приставка нужна, чтобы
# при пересчёте отличить наши индексы от чужих и снять лишние.
ATTR_INDEX_PREFIX = 'coop_resource__attrs_'
# Ключ характеристики попадает в текст DDL, куда параметр не подставишь,
# поэтому перед подстановкой он проверяется ещё раз, а не только при
# записи в справочник.
CODE_RE = re.compile(r'[a-z][a-z0-9_]{0,40}')

_logger = logging.getLogger(__name__)


class CoopResourceCategory(models.Model):
    """Рубрика знает, какие у её объявлений характеристики."""

    _inherit = 'coop.resource.category'

    attribute_assignment_ids = fields.One2many(
        'coop.attribute.assignment', 'category_id',
        string='Характеристики рубрики')
    attribute_definition = fields.PropertiesDefinition(
        string='Описание характеристик',
        compute='_compute_attribute_definition', store=True, recursive=True)

    # Пересчитывать описание надо не только когда меняют привязку, но и
    # когда правят саму характеристику: добавили вариант «Тойота» —
    # рубрика обязана его увидеть. Раньше в зависимостях стояла одна
    # ссылка `attribute_id`, то есть «привязали другую характеристику», и
    # новый вариант не доезжал до рубрики вовсе, пока кто-нибудь не
    # тронет привязку.
    @api.depends('parent_id', 'parent_path', 'parent_id.attribute_definition',
                 'attribute_assignment_ids.sequence',
                 'attribute_assignment_ids.attribute_id',
                 'attribute_assignment_ids.option_ids',
                 'attribute_assignment_ids.attribute_id.name',
                 'attribute_assignment_ids.attribute_id.code',
                 'attribute_assignment_ids.attribute_id.value_type',
                 'attribute_assignment_ids.attribute_id.unit',
                 'attribute_assignment_ids.attribute_id.show_on_card',
                 'attribute_assignment_ids.attribute_id.option_ids',
                 'attribute_assignment_ids.attribute_id.option_ids.name',
                 'attribute_assignment_ids.attribute_id.option_ids.code',
                 'attribute_assignment_ids.attribute_id.option_ids.sequence',
                 'attribute_assignment_ids.attribute_id.option_ids.active')
    def _compute_attribute_definition(self):
        """Собрать описание для движка из своего справочника.

        Справочник — источник истины, описание — производная. Наоборот
        нельзя: описание Odoo это голый список словарей без
        идентификаторов, в нём нельзя ни переиспользовать характеристику
        между рубриками, ни сопоставить словари двух узлов.

        Снятые с обращения варианты остаются в описании. Это не
        недосмотр: описание — единственное место, откуда движок узнаёт
        подпись значения, и убрав оттуда «Тойоту», мы стёрли бы её у всех
        объявлений, где она уже выбрана, при первой же их правке. Из
        панели фильтров снятый вариант при этом убирается — там он
        действительно не нужен.
        """
        for category in self:
            # По коду, а не списком: одну характеристику могли повесить и
            # на ветку, и на лист — «состояние» на «Хобби» и на его
            # «Велосипедах». Движок такое описание отвергает целиком, и
            # рубрика осталась бы вовсе без характеристик. Побеждает
            # более частная: её вешали, зная про общую.
            definition = {}
            for assignment in category._effective_assignments():
                attribute = assignment.attribute_id
                definition[attribute.code] = assignment._definition_item()
            category.attribute_definition = list(definition.values())

    def _effective_assignments(self):
        """Свои характеристики и все родительские, лист последним.

        «Транспорт → Автомобили → Легковые»: год выпуска висит на
        транспорте, марка на автомобилях, тип кузова на легковых, а
        объявление получает все три. Считается по пути в дереве, который
        рубрики и так хранят.
        """
        self.ensure_one()
        ancestors = [int(part) for part in (self.parent_path or '').split('/')
                     if part]
        if not ancestors:
            ancestors = [self.id]
        # Снятая с обращения характеристика в описание не попадает: иначе
        # флажок «Активна» в её карточке ничего не значил бы, а он ровно
        # для того и заведён — вывести характеристику из оборота, не
        # трогая привязки и не теряя уже записанные значения.
        assignments = self.env['coop.attribute.assignment'].sudo().search(
            [('category_id', 'in', ancestors), ('attribute_id.active', '=', True)])
        depth = {cid: index for index, cid in enumerate(ancestors)}
        return assignments.sorted(
            key=lambda a: (depth.get(a.category_id.id, 0), a.sequence, a.id))


class CoopResource(models.Model):
    """Объявление хранит значения характеристик своей рубрики."""

    _inherit = ['coop.resource', 'coop.attrs.mixin']
    _name = 'coop.resource'

    attrs = fields.Properties(
        string='Характеристики',
        definition='category_id.attribute_definition',
        copy=True,
        help='Набор полей зависит от рубрики: у автомобиля пробег и '
             'коробка, у металлопроката марка стали и толщина.')

    def _coop_catalog_filters(self, domain):
        """Дополнить панель характеристиками выбранной рубрики.

        Пока рубрика не выбрана, характеристик в панели нет — и это не
        недоделка: у «Марки стали» и «Пробега» нет общего смысла, а
        полсотни полей разом превратили бы фильтр в анкету. Ровно так же
        ведут себя маркетплейсы: сначала рубрика, потом её поля.
        """
        blocks = super()._coop_catalog_filters(domain)
        category = self._coop_filter_category(domain)
        # Параметры появляются, когда выбран подраздел без вложенных:
        # у раздела «Недвижимость» нет общего смысла в «этаже» и «пробеге».
        if not category or category.child_ids:
            return blocks

        return self._coop_attr_merge(
            blocks, self._coop_attr_blocks(
                domain, category.attribute_definition))

    # ── Индексы по характеристикам ──────────────────────────────────────

    def init(self):
        """Держать индексы по «частым фильтрам» в согласии со справочником.

        Признак «Частый фильтр» до сих пор был подписью в карточке
        характеристики и ничего не делал: в базе не было ни одного
        индекса по значениям, и отбор «год не раньше 2015» читал таблицу
        целиком. На сотне объявлений это незаметно, на сотнях тысяч —
        секунды на каждый щелчок в панели.

        Индекс строится по выражению `attrs -> 'ключ'`, потому что именно
        так движок и пишет условие. Обычный индекс по всей колонке здесь
        не годится: GIN умеет «содержит», но не «больше или равно», а
        диапазоны — это ровно то, ради чего признак и заведён.

        Индекс на каждую характеристику завёл бы сотню индексов на одну
        таблицу и замедлил бы запись — поэтому список задаётся вручную,
        флажком, а не выводится сам.
        """
        super().init()
        self._coop_sync_attribute_indexes()

    @api.model
    def _coop_sync_attribute_indexes(self):
        """Привести индексы в соответствие со справочником.

        Построение индекса блокирует запись в таблицу объявлений на всё
        время работы, а на живом узле с сотнями тысяч объявлений это
        десятки секунд. Строить их без блокировки (`CONCURRENTLY`) внутри
        транзакции нельзя — Postgres такого не допускает, а переключение
        флажка приходит обычной правкой записи. Поэтому флажок переключают
        в спокойное время, и об этом сказано в подсказке к нему.
        """
        cr = self.env.cr
        attributes = self.env['coop.attribute'].sudo().search(
            [('is_indexed', '=', True), ('active', '=', True)])
        desired = {}
        for attribute in attributes:
            code = attribute.code or ''
            if not CODE_RE.fullmatch(code):
                continue
            desired['%s%s_index' % (ATTR_INDEX_PREFIX, code)] = code
        cr.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'coop_resource'"
            " AND indexname LIKE %s",
            [ATTR_INDEX_PREFIX.replace('_', r'\_') + '%'])
        existing = {row[0] for row in cr.fetchall()}
        for name in existing - set(desired):
            _logger.info('Снимаем индекс по характеристике: %s', name)
            cr.execute(SQL('DROP INDEX IF EXISTS %s', SQL.identifier(name)))
        for name, code in desired.items():
            if name in existing:
                continue
            _logger.info('Строим индекс по характеристике «%s»: %s', code, name)
            cr.execute(SQL(
                'CREATE INDEX %s ON coop_resource ((attrs -> %s))',
                SQL.identifier(name), code))
        return True

    def _coop_filter_category(self, domain):
        """Рубрика, выбранная в панели, если она одна."""
        Category = self.env['coop.resource.category']
        chosen = Category
        for leaf in domain or []:
            if (isinstance(leaf, (list, tuple)) and len(leaf) == 3
                    and leaf[0] == 'category_id'
                    and leaf[1] in ('=', 'child_of')):
                chosen |= Category.sudo().browse(int(leaf[2])).exists()
        # Выбрано несколько уровней цепочки «раздел → подраздел» — берём
        # самый глубокий.
        return max(chosen, key=lambda c: (c.parent_path or '').count('/'),
                   default=Category)
