# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# Типы значений. Список ровно повторяет то, что понимает штатный
# механизм свойств Odoo: тип, которого там нет, нечем ни хранить, ни
# показать готовым виджетом, и пришлось бы писать своё поле ввода.
VALUE_TYPES = [
    ('integer', 'Целое число'),
    ('float', 'Дробное число'),
    ('boolean', 'Да или нет'),
    ('char', 'Строка'),
    ('date', 'Дата'),
    ('selection', 'Один из списка'),
    ('tags', 'Несколько из списка'),
]


class CoopAttribute(models.Model):
    """Характеристика: «Пробег», «Марка стали», «Количество комнат».

    Справочник общий на всю платформу, а не набор полей внутри рубрики.
    Марка автомобиля нужна и в «Автомобилях», и в «Запчастях»; заводить
    её дважды значит получить два несводимых списка марок и два фильтра,
    которые ищут разное под одним названием.
    """

    _name = 'coop.attribute'
    _description = 'Характеристика'
    _order = 'sequence, name'

    name = fields.Char(string='Название', required=True, translate=True)
    code = fields.Char(
        string='Ключ', required=True, index=True, copy=False,
        help='Латиницей, строчными, через подчёркивание. Это адрес '
             'значения в записи объявления, а не подпись на экране: '
             'после первого использования не меняется.')
    value_type = fields.Selection(
        VALUE_TYPES, string='Тип значения', required=True, default='selection')

    unit = fields.Char(
        string='Единица',
        help='км, м², мм, кг. Показывается справа от поля.')
    value_min = fields.Float(string='Не меньше')
    value_max = fields.Float(string='Не больше')

    # Тип значения и способ фильтровать — разные вещи. Одно и то же целое
    # число фильтруют то флажками (комнат: 1, 2, 3), то диапазоном
    # (пробег). Свести их в одно поле значит потерять этот выбор.
    filter_widget = fields.Selection([
        ('none', 'Не фильтруется'),
        ('checkbox', 'Флажки'),
        ('select', 'Выпадающий список'),
        ('range', 'Диапазон от и до'),
        ('switch', 'Да или нет'),
    ], string='Как фильтруется', required=True, default='checkbox')

    is_indexed = fields.Boolean(
        string='Частый фильтр',
        help='По таким характеристикам строится индекс в базе: без него '
             'отбор «год не раньше 2015» читает таблицу объявлений целиком. '
             'Индекс на каждую — это сотня индексов на одну таблицу и '
             'заметно более медленная запись, поэтому отмечают только те, '
             'по которым действительно ищут. Переключать флажок лучше в '
             'спокойное время: построение индекса блокирует запись в '
             'объявления, и на большом узле это десятки секунд.')
    show_on_card = fields.Boolean(string='Показывать в карточке')
    help_text = fields.Char(string='Подсказка')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    option_ids = fields.One2many(
        'coop.attribute.option', 'attribute_id', string='Варианты значений')
    assignment_ids = fields.One2many(
        'coop.attribute.assignment', 'attribute_id', string='Где применяется')

    _code_uniq = models.Constraint(
        'unique(code)',
        'Характеристика с таким ключом уже есть.',
    )

    @api.constrains('code')
    def _check_code(self):
        for record in self:
            if not record.code or not all(
                    c.islower() or c.isdigit() or c == '_' for c in record.code):
                raise ValidationError(_(
                    'Ключ «%s» не годится: только строчные латинские буквы, '
                    'цифры и подчёркивание.') % record.code)

    def _listing_count(self):
        """Сколько объявлений уже хранят значение по этому ключу.

        Спрашиваем саму колонку значений, а не привязки к рубрикам.
        Привязку можно снять, а значения при этом остаются лежать в
        объявлениях: проверять по привязкам значит разрешить смену ключа
        ровно в тот момент, когда данные уже есть, но связь с рубрикой
        временно убрана.
        """
        self.ensure_one()
        if not self.code:
            return 0
        self.env['coop.resource'].flush_model(['attrs'])
        self.env.cr.execute(
            'SELECT count(*) FROM coop_resource WHERE attrs ? %s', (self.code,))
        return self.env.cr.fetchone()[0]

    def write(self, vals):
        """Ключ не меняется после того, как им начали пользоваться.

        Ключ — адрес значения внутри объявления. Смена ключа не
        переносит значения, а делает их невидимыми: данные остаются
        лежать, но их больше никто не читает. Подпись при этом меняется
        свободно — она и есть то, что человек видит.
        """
        if 'code' in vals:
            for record in self:
                if record.code == vals['code']:
                    continue
                if record.assignment_ids:
                    raise ValidationError(_(
                        'Характеристика «%s» уже привязана к рубрикам — '
                        'ключ менять нельзя, у объявлений пропадут '
                        'значения. Меняйте название.') % record.name)
                used = record._listing_count()
                if used:
                    raise ValidationError(_(
                        'По ключу «%(code)s» уже хранят значения %(count)s '
                        'объявлений. Смена ключа не переносит их, а делает '
                        'невидимыми. Меняйте название.') % {
                            'code': record.code, 'count': used})
        result = super().write(vals)
        if 'is_indexed' in vals or 'value_type' in vals or 'active' in vals:
            self.env['coop.resource']._coop_sync_attribute_indexes()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if any(v.get('is_indexed') for v in vals_list):
            self.env['coop.resource']._coop_sync_attribute_indexes()
        return records

    def unlink(self):
        """Характеристику, по которой уже есть значения, не удаляем.

        Удаление снимает привязки каскадом, значения же остаются в
        объявлениях мусором: показать их нечем, найти нечем, вычистить
        некому. Ненужную характеристику убирают из обращения флажком
        «Активна» — тогда и данные целы, и в новых объявлениях её нет.
        """
        for record in self:
            used = record._listing_count()
            if used:
                raise ValidationError(_(
                    'Характеристику «%(name)s» хранят %(count)s объявлений. '
                    'Удаление оставит их значения мусором в базе — снимите '
                    'флажок «Активна» вместо удаления.') % {
                        'name': record.name, 'count': used})
        result = super().unlink()
        self.env['coop.resource']._coop_sync_attribute_indexes()
        return result


class CoopAttributeOption(models.Model):
    """Вариант значения: «Тойота», «Механическая», «Ст3сп».

    Отдельная модель, а не список строк внутри характеристики: у
    вариантов должны быть устойчивые ключи. Иначе переименование
    «Тойота» в «Toyota» обнулит фильтр у всех объявлений разом.
    """

    _name = 'coop.attribute.option'
    _description = 'Вариант значения характеристики'
    _order = 'attribute_id, sequence, name'

    attribute_id = fields.Many2one(
        'coop.attribute', string='Характеристика', required=True,
        index=True, ondelete='cascade')
    name = fields.Char(string='Название', required=True, translate=True)
    code = fields.Char(string='Ключ', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        'unique(attribute_id, code)',
        'Такой вариант у этой характеристики уже есть.',
    )

    def _listing_count(self):
        """Сколько объявлений выбрали именно этот вариант.

        Учитываем оба способа хранения: у «одного из списка» значение
        лежит строкой, у «нескольких из списка» — массивом строк.
        """
        self.ensure_one()
        code = self.attribute_id.code
        if not code or not self.code:
            return 0
        self.env['coop.resource'].flush_model(['attrs'])
        self.env.cr.execute(
            """SELECT count(*) FROM coop_resource
                WHERE attrs -> %s = to_jsonb(%s::text)
                   OR attrs -> %s @> to_jsonb(ARRAY[%s]::text[])""",
            (code, self.code, code, self.code))
        return self.env.cr.fetchone()[0]

    def unlink(self):
        """Вариант, который уже выбран в объявлениях, не удаляем.

        Удаление варианта не вычищает значения: они остаются в
        объявлениях, но пропадают из описания рубрики. Движок свойств
        стирает такое значение при первой же правке объявления, а до тех
        пор оно не показывается и не находится фильтром — объявление
        молча выпадает из выдачи, и владелец об этом не узнает.
        """
        for record in self:
            used = record._listing_count()
            if used:
                raise ValidationError(_(
                    'Вариант «%(name)s» выбран в %(count)s объявлениях. '
                    'Удаление обнулит его у них — снимите флажок «Активен», '
                    'тогда он исчезнет из выбора, а выбранное уцелеет.') % {
                        'name': record.name, 'count': used})
        return super().unlink()


class CoopAttributeAssignment(models.Model):
    """Привязка характеристики к рубрике.

    Отдельной записью, а не полем-списком у рубрики: у привязки есть
    свои свойства — порядок в панели, обязательность при публикации и
    сокращённый набор вариантов. У «Марки» в грузовиках список короче,
    чем в легковых, а характеристика одна и та же.
    """

    _name = 'coop.attribute.assignment'
    _description = 'Характеристика рубрики'
    _order = 'sequence, id'

    attribute_id = fields.Many2one(
        'coop.attribute', string='Характеристика', required=True,
        index=True, ondelete='cascade')
    category_id = fields.Many2one(
        'coop.resource.category', string='Рубрика', required=True,
        index=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    is_required = fields.Boolean(string='Обязательна при публикации')
    option_ids = fields.Many2many(
        'coop.attribute.option', string='Разрешённые варианты',
        help='Пусто — годятся все варианты характеристики.')

    _uniq = models.Constraint(
        'unique(attribute_id, category_id)',
        'Эта характеристика уже привязана к рубрике.',
    )
