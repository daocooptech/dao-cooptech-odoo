# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CoopOkved(models.Model):
    """Вид экономической деятельности по ОКВЭД.

    Зачем отдельный справочник. До 15 сентября 2026 организации в
    каталоге раскладывались по «сфере деятельности» — справочнику из
    мира вакансий. Результат был виден по данным: у одиннадцати
    кооперативов сфера значилась как «Рабочий персонал», у десяти —
    «Финансы, бухгалтерия». Для человека, ищущего работу, это
    осмысленно; для организации нет: это не то, чем она занимается.

    ОКВЭД лучше тремя вещами. Он официальный — на него ссылаются устав,
    отчётность и налоговый режим. Он **уже есть** у каждого
    зарегистрированного юрлица, и заполнять его руками не нужно: он
    приходит из выписки. И он один на всю страну, поэтому по нему
    сходятся кооператив в Вологде и союз в Иркутске.

    Дерево двухуровневое: раздел (буква A–U) и класс (две цифры).
    Полных кодов в классификаторе около двух с половиной тысяч — по ним
    полку не построишь, да и организации редко нужен такой разбор.
    Полный код, как он написан в выписке, хранится строкой у самой
    организации: он нужен для точного поиска и для сверки с реестром.
    """
    _name = 'coop.okved'
    _description = 'Вид деятельности по ОКВЭД'
    _order = 'code'
    _parent_store = True

    name = fields.Char(string='Название', required=True, translate=False)
    code = fields.Char(
        string='Код', required=True, index=True,
        help='Буква раздела (A) или две цифры класса (01).')
    parent_id = fields.Many2one(
        'coop.okved', string='Раздел', index=True, ondelete='cascade',
        help='У класса — раздел, в который он входит. У раздела пусто.')
    parent_path = fields.Char(index=True, unaccent=False)
    child_ids = fields.One2many('coop.okved', 'parent_id', string='Классы')
    active = fields.Boolean(default=True)

    display_name = fields.Char(compute='_compute_display_name', store=True)

    _code_uniq = models.Constraint(
        'unique(code)',
        'Такой код ОКВЭД уже заведён: классификатор один на всех.',
    )

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for record in self:
            # Код первым: по нему сверяют с выпиской, и искать удобнее
            # по нему же.
            record.display_name = '%s %s' % (record.code or '', record.name or '')

    @api.constrains('parent_id')
    def _check_depth(self):
        """Дерево ровно в два уровня.

        Классификатор глубже — до шести знаков, — но нам нужны раздел и
        класс: первый для полок, второй для отбора. Третий уровень
        означал бы, что мы копируем справочник целиком, а он большой и
        меняется приказами Росстандарта.
        """
        for record in self:
            if record.parent_id and record.parent_id.parent_id:
                raise ValidationError(_(
                    'Справочник ОКВЭД здесь двухуровневый: раздел и класс. '
                    'Полный код хранится у самой организации строкой.'))

    @api.model
    def _coop_by_code(self, code):
        """Запись по коду. Пусто, если такого кода нет."""
        if not code:
            return self.browse()
        return self.search([('code', '=', code)], limit=1)
