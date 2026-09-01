# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoopLegalFormGroup(models.Model):
    """Группа правовых форм — коммерческие, некоммерческие, кооперативные.

    Группа нужна отдельно от формы, потому что почти все правила платформы
    формулируются на её уровне, а не на уровне конкретной формы: кто может
    вступить в кооперативную сеть, кто распределяет прибыль между
    участниками, к кому применимы правила о паевых взносах.
    """
    _name = 'coop.legal.form.group'
    _description = 'Группа правовых форм'
    _order = 'sequence, name'

    name = fields.Char(string='Название', required=True)
    code = fields.Char(string='Код', required=True)
    sequence = fields.Integer(string='Порядок', default=10)
    form_ids = fields.One2many('coop.legal.form', 'group_id', string='Формы')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Такая группа уже есть.'),
    ]


class CoopLegalForm(models.Model):
    """Организационно-правовая форма организации.

    Справочник, а не поле-перечисление, и это решение владельца от
    2026-09-01. Причина в том, что от формы зависят правила: кто может
    быть пайщиком, кто вправе выпускать цифровые права, кто как
    отчитывается и по какому закону вообще существует. В перечислении эти
    правила пришлось бы держать в коде — здесь они становятся данными,
    которые правит юрист, а не разработчик.

    Флаги ниже — не украшение, а те самые правила в машиночитаемом виде.
    Пока их читает только интерфейс, но именно на них будут опираться
    проверки, когда дойдёт дело до паёв и расчётов.
    """
    _name = 'coop.legal.form'
    _description = 'Правовая форма'
    _order = 'sequence, name'

    name = fields.Char(string='Название', required=True)
    short_name = fields.Char(
        string='Сокращение', required=True,
        help='Как форма пишется в названии организации: ООО, ПК, СПК, ТСЖ.')
    code = fields.Char(string='Код', required=True)
    group_id = fields.Many2one(
        'coop.legal.form.group', string='Группа', required=True,
        ondelete='restrict')
    sequence = fields.Integer(string='Порядок', default=10)

    law = fields.Char(
        string='Основание',
        help='Закон, которым форма учреждена. Нужен не для справки: от него '
             'зависит, какие правила к организации вообще применимы.')

    has_members = fields.Boolean(
        string='Есть участники или пайщики', default=False,
        help='У формы есть члены со взносами и правом голоса. Для таких '
             'организаций имеет смысл раздел членства, для остальных — нет.')
    is_cooperative = fields.Boolean(
        string='Кооперативная форма', default=False,
        help='Организация кооперативного типа: голосование по принципу '
             '«один участник — один голос», распределение по труду и '
             'участию, а не по долям в капитале.')
    is_russian = fields.Boolean(
        string='Форма по праву РФ', default=True,
        help='Снято у форм, которых в российском праве нет. Такая '
             'организация может участвовать в сети, но зарегистрирована '
             'она в другой юрисдикции либо не является юридическим лицом '
             'вовсе — и правила о паях и расчётах к ней неприменимы.')

    partner_ids = fields.One2many(
        'res.partner', 'coop_legal_form_id', string='Организации')
    partner_count = fields.Integer(
        string='Организаций', compute='_compute_partner_count')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Такая правовая форма уже есть.'),
    ]

    @api.depends('partner_ids')
    def _compute_partner_count(self):
        for record in self:
            record.partner_count = len(record.partner_ids)

    @api.depends('name', 'short_name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = '%s — %s' % (record.short_name, record.name)
