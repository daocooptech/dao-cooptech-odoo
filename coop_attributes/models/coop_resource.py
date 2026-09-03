# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoopResourceCategory(models.Model):
    """Рубрика знает, какие у её объявлений характеристики."""

    _inherit = 'coop.resource.category'

    attribute_assignment_ids = fields.One2many(
        'coop.attribute.assignment', 'category_id',
        string='Характеристики рубрики')
    attribute_definition = fields.PropertiesDefinition(
        string='Описание характеристик',
        compute='_compute_attribute_definition', store=True, recursive=True)

    @api.depends('parent_id.attribute_definition',
                 'attribute_assignment_ids.sequence',
                 'attribute_assignment_ids.attribute_id',
                 'attribute_assignment_ids.option_ids')
    def _compute_attribute_definition(self):
        """Собрать описание для движка из своего справочника.

        Справочник — источник истины, описание — производная. Наоборот
        нельзя: описание Odoo это голый список словарей без
        идентификаторов, в нём нельзя ни переиспользовать характеристику
        между рубриками, ни сопоставить словари двух узлов.
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
                item = {
                    'name': attribute.code,
                    'string': attribute.name,
                    'type': attribute.value_type,
                }
                if attribute.unit:
                    item['suffix'] = attribute.unit
                if attribute.value_type == 'selection':
                    options = assignment.option_ids or attribute.option_ids
                    item['selection'] = [[o.code, o.name] for o in options]
                elif attribute.value_type == 'tags':
                    options = assignment.option_ids or attribute.option_ids
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
        assignments = self.env['coop.attribute.assignment'].sudo().search(
            [('category_id', 'in', ancestors)])
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

        В хранилище значений строки и числа сортируются раздельно:
        «84000» строкой окажется за пределами диапазона «пробег до
        100 000», и объявление молча выпадет из выдачи. Ошибки при этом
        не будет никакой.
        """
        for record in self:
            for key, value in (record.attrs or {}).items():
                if isinstance(value, str) and value.strip():
                    stripped = value.strip().replace(',', '.')
                    try:
                        float(stripped)
                    except ValueError:
                        continue
                    attribute = self.env['coop.attribute'].sudo().search(
                        [('code', '=', key)], limit=1)
                    if attribute and attribute.value_type in ('integer', 'float'):
                        raise ValidationError(_(
                            'Характеристика «%s» — число, а записано '
                            'строкой. Так объявление выпадет из фильтра по '
                            'диапазону.') % attribute.name)

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

        extra = []
        for item in category.attribute_definition or []:
            code = item.get('name')
            kind = item.get('type')
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
                block['options'] = [{'value': value, 'label': label}
                                    for value, label in item.get('selection') or []]
            elif kind == 'tags':
                # Метка ищется вхождением: у объявления их несколько, и
                # равенство списку не сработало бы.
                block['widget'] = 'select'
                block['operator'] = 'in'
                block['placeholder'] = 'Любое'
                block['options'] = [{'value': tag[0], 'label': tag[1]}
                                    for tag in item.get('tags') or []]
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

    def _coop_filter_category(self, domain):
        """Рубрика, выбранная в панели, если она одна."""
        for leaf in domain or []:
            if (isinstance(leaf, (list, tuple)) and len(leaf) == 3
                    and leaf[0] == 'category_id' and leaf[1] == '='):
                category = self.env['coop.resource.category'].sudo().browse(
                    int(leaf[2]))
                return category.exists()
        return self.env['coop.resource.category']
