# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoopSpecializationCategory(models.Model):
    """Сфера деятельности — верхний уровень справочника специализаций.

    В макете каталог открывается не списком из ста записей, а перечнем
    специализаций: «Рабочий персонал», «ИТ и разработка», «Финансы».
    Ищут от того, что нужно сделать, а не от названия.
    """
    _name = 'coop.specialization.category'
    _description = 'Сфера деятельности'
    _order = 'name'

    name = fields.Char(string='Название', required=True, translate=False)
    specialization_ids = fields.One2many(
        'coop.specialization', 'category_id', string='Специализации')
    specialization_count = fields.Integer(
        string='Специализаций', compute='_compute_counts')
    partner_count = fields.Integer(
        string='Людей', compute='_compute_counts')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Такая сфера деятельности уже есть.'),
    ]

    @api.depends('specialization_ids.partner_count')
    def _compute_counts(self):
        for record in self:
            record.specialization_count = len(record.specialization_ids)
            record.partner_count = sum(record.specialization_ids.mapped('partner_count'))


class CoopSpecialization(models.Model):
    """Специализация — чем занимается человек или организация.

    Справочник один на все каталоги: люди, организации, вакансии и навыки
    ссылаются на одни и те же записи. Разбор макета показал, что это
    возможно без противоречий — 26 сфер и 57 специализаций, и ни одна
    специализация не встречается в двух сферах сразу.

    Отдельно от навыков, и это не придирка. Специализация одна и отвечает
    на вопрос «кто это»; навыков много, и они отвечают на вопрос «что он
    возьмётся сделать». Сварщик, умеющий варить и класть кирпич, — это
    один сварщик с двумя навыками, а не два человека.

    Ресурсы сюда не входят: под теми же атрибутами макета у них лежит
    дерево товарных категорий (Недвижимость, Транспорт, Электроника), а
    это вид товара, а не специализация исполнителя. Ему место в
    product.category.
    """
    _name = 'coop.specialization'
    _description = 'Специализация'
    _order = 'name'

    name = fields.Char(string='Название', required=True)
    category_id = fields.Many2one(
        'coop.specialization.category', string='Сфера деятельности',
        required=True, ondelete='restrict')
    partner_ids = fields.One2many(
        'res.partner', 'coop_specialization_id', string='Люди и организации')
    partner_count = fields.Integer(
        string='Записей', compute='_compute_partner_count', store=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Такая специализация уже есть.'),
    ]

    @api.depends('partner_ids.coop_is_participant')
    def _compute_partner_count(self):
        for record in self:
            record.partner_count = len(
                record.partner_ids.filtered('coop_is_participant'))
