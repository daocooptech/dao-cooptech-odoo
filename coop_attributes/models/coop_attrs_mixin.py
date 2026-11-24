# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import SQL


class CoopAttrsMixin(models.AbstractModel):
    """Запись с набором характеристик из справочника.

    Объявление берёт набор у рубрики, вакансия и предложение навыка — у
    специализации (№ 483). Само поле `attrs` заводит наследник: у каждого
    своё описание.
    """

    _name = 'coop.attrs.mixin'
    _description = 'Запись с характеристиками'

    # Витрина показывает только заполненное, как «О квартире» у Авито:
    # стандартный виджет характеристик выводит и пустые строки, и у
    # объявления с двумя значениями из двенадцати карточка читалась бы
    # как недозаполненная анкета (владелец 23.11.2026, № 483).
    attrs_facts = fields.Html(
        string='Характеристики (витрина)',
        compute='_compute_attrs_facts', sanitize=False)

    @api.depends(lambda self: (
        'attrs', self._fields['attrs'].definition_record)
        if 'attrs' in self._fields else ())
    def _compute_attrs_facts(self):
        for record in self:
            items = []
            # Значение поля на записи — словарь «ключ → значение», где у
            # меток уже склеенная строка и нет подписей вариантов. Формат
            # чтения отдаёт описание вместе со значением — его и берём.
            field = record._fields['attrs']
            props = field.convert_to_read(
                record.attrs._values if record.attrs else {}, record,
                use_display_name=False) if record.id else []
            for prop in props or []:
                text = record._coop_attr_text(prop)
                if text:
                    items.append(Markup(
                        '<div><dt>%s</dt><dd>%s</dd></div>')
                        % (prop.get('string') or '', text))
            record.attrs_facts = (
                Markup('<dl class="coop-show_facts coop-attrs_facts">%s</dl>')
                % Markup('').join(items)) if items else False

    @staticmethod
    def _coop_attr_text(prop):
        """Значение характеристики словами; пустое — пустая строка."""
        value = prop.get('value')
        kind = prop.get('type')
        if value in (None, False, '', []) and kind != 'boolean':
            return ''
        if kind == 'boolean':
            # «Нет» у флажка — не ответ, а незаполненное поле: продавец
            # мог просто не дойти до него. Показываем только «да».
            return 'да' if value else ''
        if kind == 'selection':
            labels = dict(prop.get('selection') or [])
            text = labels.get(value, '')
        elif kind == 'tags':
            labels = {t[0]: t[1] for t in prop.get('tags') or []}
            text = ', '.join(labels[v] for v in value if v in labels)
        elif kind == 'float':
            text = ('%g' % value).replace('.', ',')
        elif kind == 'integer':
            # Разряды — только с пяти знаков: «120 000 км», но «1990», а
            # не «1 990» в годе постройки.
            text = ('{:,}'.format(value).replace(',', ' ')
                    if abs(value) >= 10000 else str(value))
        elif kind == 'date':
            text = fields.Date.to_date(value).strftime('%d.%m.%Y')
        else:
            text = str(value)
        if text and prop.get('suffix'):
            text = '%s %s' % (text, prop['suffix'])
        return text

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

    def _coop_attr_blocks(self, domain, definition):
        """Блоки панели фильтров по описанию характеристик."""
        # Как характеристика фильтруется, задано в справочнике отдельным
        # полем, и раньше оно ни на что не влияло: панель выводила поле
        # по типу значения, а «Не фильтруется» просто не соблюдалось.
        # Заодно отсюда берём снятые с обращения варианты: в описании они
        # остаются ради уже записанных значений, а в панели им не место.
        definition = definition or []
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

        # Флажки («Как фильтруется» = «Флажки») выводятся пилюлями с
        # множественным выбором и счётчиками, как у Авито и Юлы; прежний
        # выпадающий список брал за раз одно значение. Счётчики считает
        # `_coop_attr_counts` — одним запросом на всю рубрику.
        def pills(item):
            attribute = by_code.get(item.get('name'))
            wanted = attribute.filter_widget if attribute else 'checkbox'
            return (wanted == 'checkbox'
                    and item.get('type') in ('selection', 'tags',
                                             'integer'))

        counted = [item.get('name') for item in definition
                   if item.get('name') and pills(item)]
        counts = self._coop_attr_counts(domain, counted) if counted else {}

        extra = []
        for item in definition:
            code = item.get('name')
            kind = item.get('type')
            attribute = by_code.get(code)
            if attribute and attribute.filter_widget == 'none':
                continue
            if pills(item):
                found = counts.get(code, {})
                if kind == 'integer':
                    # Целое с флажками (комнат, оперативная память): варианты
                    # — те числа, что есть у объявлений.
                    values = sorted(found, key=lambda v: float(v))
                    options = [{'value': float(v) if '.' in v else int(v),
                                'label': v, 'count': found[v]}
                               for v in values]
                    if not options:
                        continue
                else:
                    source = (item.get('selection') if kind == 'selection'
                              else item.get('tags')) or []
                    options = [
                        {'value': pair[0], 'label': pair[1],
                         'count': found.get(pair[0], 0)}
                        for pair in source if (code, pair[0]) not in retired]
                extra.append({
                    'code': 'attr_%s' % code,
                    'field': 'attrs.%s' % code,
                    'label': item.get('string') or code,
                    'unit': item.get('suffix') or '',
                    'widget': 'multi', 'pills': True,
                    'number': kind == 'integer',
                    'options': options,
                })
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
        return extra

    @staticmethod
    def _coop_attr_merge(blocks, extra):
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
                      FROM %s WHERE id IN %s
                ) t WHERE v IS NOT NULL GROUP BY 1, 2
                """,
                plain, values, SQL.identifier(self._table), subselect))
            for key, value, count in self.env.cr.fetchall():
                counts.setdefault(key, {})[value] = count
        for code in tagged:
            self.env.cr.execute(SQL(
                """
                SELECT e.elem, count(*)
                  FROM %s r,
                       LATERAL jsonb_array_elements_text(
                           CASE WHEN jsonb_typeof(r.attrs -> %s) = 'array'
                                THEN r.attrs -> %s ELSE '[]'::jsonb END) e(elem)
                 WHERE r.id IN %s
                 GROUP BY 1
                """,
                SQL.identifier(self._table), code, code, subselect))
            counts[code] = {value: count
                            for value, count in self.env.cr.fetchall()}
        return counts
