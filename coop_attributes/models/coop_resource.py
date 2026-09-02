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
            definition = []
            for assignment in category._effective_assignments():
                attribute = assignment.attribute_id
                item = {
                    'name': attribute.code,
                    'string': attribute.name,
                    'type': attribute.value_type,
                }
                if attribute.unit:
                    item['suffix'] = attribute.unit
                if attribute.value_type in ('selection', 'tags'):
                    options = assignment.option_ids or attribute.option_ids
                    key = ('selection' if attribute.value_type == 'selection'
                           else 'tags')
                    item[key] = [[o.code, o.name] for o in options]
                if attribute.show_on_card:
                    item['view_in_cards'] = True
                definition.append(item)
            category.attribute_definition = definition

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
