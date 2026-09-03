# -*- coding: utf-8 -*-
import logging
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
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
                # Снятые с обращения варианты нужны описанию — см.
                # объяснение в строке документации выше.
                all_options = assignment.with_context(
                    active_test=False).option_ids or attribute.with_context(
                        active_test=False).option_ids
                item = {
                    'name': attribute.code,
                    'string': attribute.name,
                    'type': attribute.value_type,
                }
                if attribute.unit:
                    item['suffix'] = attribute.unit
                if attribute.value_type == 'selection':
                    options = all_options
                    item['selection'] = [[o.code, o.name] for o in options]
                elif attribute.value_type == 'tags':
                    options = all_options
                    # У метки, в отличие от варианта выбора, третьим идёт
                    # номер цвета: движок проверяет длину, и пара из двух
                    # элементов до записи не доходит.
                    item['tags'] = [[o.code, o.name, index % 11]
                                    for index, o in enumerate(options)]
                if attribute.show_on_card:
                    item['view_in_cards'] = True
                definition[attribute.code] = item
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

    _inherit = 'coop.resource'

    attrs = fields.Properties(
        string='Характеристики',
        definition='category_id.attribute_definition',
        copy=True,
        help='Набор полей зависит от рубрики: у автомобиля пробег и '
             'коробка, у металлопроката марка стали и толщина.')

    @api.constrains('attrs')
    def _check_attrs_types(self):
        """Число должно храниться числом, а не строкой.

        Значения лежат в jsonb, и сравнение там идёт по типам: любая
        строка больше любого числа. Проверено на стенде — «две тысячи
        пятнадцатый» в поле «Год выпуска» попадает во все диапазоны «от»
        и не попадает ни в один «до». Ошибки при этом никакой: объявление
        просто оказывается не там, где его ищут.

        Поэтому строка в числовой характеристике не годится никакая, а не
        только та, которая похожа на число. Заодно проверяем границы
        «не меньше» и «не больше» из справочника: без этого они остаются
        подписью в карточке характеристики, ни на что не влияющей.
        """
        # Справочник спрашиваем один раз на всю пачку, а не на каждый
        # ключ каждой записи: при загрузке каталога это была сотня
        # одинаковых запросов подряд.
        codes = {key for record in self for key in (record.attrs or {})}
        if not codes:
            return
        attributes = self.env['coop.attribute'].sudo().with_context(
            active_test=False).search_fetch(
                [('code', 'in', list(codes))],
                ['code', 'name', 'value_type', 'value_min', 'value_max'])
        by_code = {a.code: a for a in attributes}
        for record in self:
            for key, value in (record.attrs or {}).items():
                attribute = by_code.get(key)
                if not attribute or attribute.value_type not in ('integer', 'float'):
                    continue
                if value in (None, False, ''):
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValidationError(_(
                        'Характеристика «%(name)s» — число, а записано '
                        '«%(value)s». Так объявление выпадет из фильтра по '
                        'диапазону: в хранилище значений строка считается '
                        'больше любого числа.') % {
                            'name': attribute.name, 'value': value})
                if attribute.value_min and value < attribute.value_min:
                    raise ValidationError(_(
                        'Характеристика «%(name)s»: %(value)s меньше '
                        'допустимого %(limit)s.') % {
                            'name': attribute.name, 'value': value,
                            'limit': attribute.value_min})
                if attribute.value_max and value > attribute.value_max:
                    raise ValidationError(_(
                        'Характеристика «%(name)s»: %(value)s больше '
                        'допустимого %(limit)s.') % {
                            'name': attribute.name, 'value': value,
                            'limit': attribute.value_max})

    def _coop_catalog_filters(self, domain):
        """Дополнить панель характеристиками выбранной рубрики.

        Пока рубрика не выбрана, характеристик в панели нет — и это не
        недоделка: у «Марки стали» и «Пробега» нет общего смысла, а
        полсотни полей разом превратили бы фильтр в анкету. Ровно так же
        ведут себя маркетплейсы: сначала рубрика, потом её поля.
        """
        blocks = super()._coop_catalog_filters(domain)
        category = self._coop_filter_category(domain)
        if not category:
            return blocks

        # Как характеристика фильтруется, задано в справочнике отдельным
        # полем, и раньше оно ни на что не влияло: панель выводила поле
        # по типу значения, а «Не фильтруется» просто не соблюдалось.
        # Заодно отсюда берём снятые с обращения варианты: в описании они
        # остаются ради уже записанных значений, а в панели им не место.
        definition = category.attribute_definition or []
        codes = [item.get('name') for item in definition if item.get('name')]
        attributes = self.env['coop.attribute'].sudo().with_context(
            active_test=False).search_fetch(
                [('code', 'in', codes)],
                ['code', 'filter_widget', 'help_text'])
        by_code = {a.code: a for a in attributes}
        retired = {
            (o.attribute_id.code, o.code)
            for o in self.env['coop.attribute.option'].sudo().search(
                [('attribute_id.code', 'in', codes), ('active', '=', False)])
        }

        extra = []
        for item in definition:
            code = item.get('name')
            kind = item.get('type')
            attribute = by_code.get(code)
            if attribute and attribute.filter_widget == 'none':
                continue
            block = {
                'code': 'attr_%s' % code,
                # Домен по характеристике адресуется через точку: движок
                # разбирает такой путь сам, отдельного поля заводить не
                # нужно.
                'field': 'attrs.%s' % code,
                'label': item.get('string') or code,
                'unit': item.get('suffix') or '',
            }
            if kind in ('integer', 'float'):
                block['widget'] = 'range'
                block['hint'] = 'Пустое поле — без ограничения.'
            elif kind == 'selection':
                block['widget'] = 'select'
                block['placeholder'] = 'Любое'
                block['options'] = [
                    {'value': value, 'label': label}
                    for value, label in item.get('selection') or []
                    if (code, value) not in retired]
            elif kind == 'tags':
                # Метка ищется вхождением: у объявления их несколько, и
                # равенство списку не сработало бы.
                block['widget'] = 'select'
                block['operator'] = 'in'
                block['placeholder'] = 'Любое'
                block['options'] = [
                    {'value': tag[0], 'label': tag[1]}
                    for tag in item.get('tags') or []
                    if (code, tag[0]) not in retired]
            elif kind == 'boolean':
                block['widget'] = 'quick'
                block['options'] = [{
                    'value': 'attr_%s' % code,
                    'label': item.get('string') or code,
                    'domain': [('attrs.%s' % code, '=', True)],
                }]
            else:
                continue
            extra.append(block)

        if not extra:
            return blocks
        # Характеристики встают перед быстрыми фильтрами: те — ярлыки к
        # тому, что уже перечислено выше, и должны оставаться внизу.
        quick = [b for b in blocks if b.get('widget') == 'quick']
        rest = [b for b in blocks if b.get('widget') != 'quick']
        return rest + extra + quick

    # ── Счётчики значений в панели ──────────────────────────────────────

    def _coop_attr_counts(self, domain, codes):
        """Счётчики по всем характеристикам сразу, одним запросом.

        Раньше каждое поле выбора считалось своим `_read_group`, а движок
        свойств вдобавок перечитывал описание рубрики перед каждым таким
        подсчётом. На «Легковых автомобилях» это 16 запросов на одно
        открытие каталога, из них 12 — на характеристики; на рубрике с
        двумя десятками характеристик было бы за сорок.

        Условия самой характеристики из отбора при подсчёте снимаются:
        иначе выбор «Тойота» обнулит счётчик у «Лады», и переключиться
        станет нечем. Для тех характеристик, по которым сейчас ничего не
        выбрано (а это обычный случай), общий отбор один и тот же —
        поэтому все они считаются вместе. Отдельный запрос уходит только
        на характеристику, по которой условие уже стоит.
        """
        codes = [c for c in codes if c]
        if not codes:
            return {}
        applied = {
            leaf[0].split('.', 1)[1]
            for leaf in domain or []
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3
            and isinstance(leaf[0], str) and leaf[0].startswith('attrs.')
        }
        result = {}
        # По этим характеристикам условий нет, значит вычитать из отбора
        # нечего и он у всех них один и тот же — полный. Остальные
        # применённые условия при этом остаются: счётчик коробок передач
        # должен считаться среди «Тойот», если «Тойота» уже выбрана.
        base = [c for c in codes if c not in applied]
        if base:
            result.update(self._coop_attr_count_query(domain or [], base))
        for code in codes:
            if code not in applied:
                continue
            others = [
                leaf for leaf in domain or []
                if not (isinstance(leaf, (list, tuple)) and len(leaf) == 3
                        and leaf[0] == 'attrs.%s' % code)
            ]
            result.update(self._coop_attr_count_query(others, [code]))
        return result

    def _coop_attr_count_query(self, domain, codes):
        """Одна группировка по всем перечисленным ключам характеристик.

        Идём в базу напрямую, а не через группировку движка: он умеет
        группировать по одному свойству за запрос, а нам нужны все ключи
        разом. Права при этом соблюдаются — отбор строится штатным
        поиском, и правила доступа уже внутри него.

        Ключи перечисляются поимённо и разворачиваются `unnest`, а не
        обходом всей колонки через `jsonb_each`. Замерено на 200 000
        объявлений: обход всей колонки — 736 мс, поимённый список —
        235 мс, четыре отдельные группировки движка — 428 мс. Обход
        дороже потому, что раскладывает каждую запись на все её значения,
        включая те, по которым в панели ничего не считают.

        Метки («несколько из списка») считаются отдельно: у них значение
        не строка, а массив строк, и в общий список их не свести.
        """
        codes = list(codes)
        query = self._search(domain or [])
        self.flush_model(['attrs'])
        subselect = query.subselect()
        types = {
            a.code: a.value_type
            for a in self.env['coop.attribute'].sudo().with_context(
                active_test=False).search_fetch(
                    [('code', 'in', codes)], ['code', 'value_type'])
        }
        plain = [c for c in codes if types.get(c) != 'tags']
        tagged = [c for c in codes if types.get(c) == 'tags']

        counts = {}
        if plain:
            values = SQL(', ').join(SQL('attrs ->> %s', code) for code in plain)
            self.env.cr.execute(SQL(
                """
                SELECT k, v, count(*) FROM (
                    SELECT unnest(%s::text[]) AS k, unnest(ARRAY[%s]) AS v
                      FROM coop_resource WHERE id IN %s
                ) t WHERE v IS NOT NULL GROUP BY 1, 2
                """,
                plain, values, subselect))
            for key, value, count in self.env.cr.fetchall():
                counts.setdefault(key, {})[value] = count
        for code in tagged:
            self.env.cr.execute(SQL(
                """
                SELECT e.elem, count(*)
                  FROM coop_resource r,
                       LATERAL jsonb_array_elements_text(
                           CASE WHEN jsonb_typeof(r.attrs -> %s) = 'array'
                                THEN r.attrs -> %s ELSE '[]'::jsonb END) e(elem)
                 WHERE r.id IN %s
                 GROUP BY 1
                """,
                code, code, subselect))
            counts[code] = {value: count
                            for value, count in self.env.cr.fetchall()}
        return counts

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
        for leaf in domain or []:
            if (isinstance(leaf, (list, tuple)) and len(leaf) == 3
                    and leaf[0] == 'category_id' and leaf[1] == '='):
                category = self.env['coop.resource.category'].sudo().browse(
                    int(leaf[2]))
                return category.exists()
        return self.env['coop.resource.category']
