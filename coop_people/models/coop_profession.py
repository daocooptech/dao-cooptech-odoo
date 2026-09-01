# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoopProfessionCategory(models.Model):
    """Категория специализаций — верхний уровень каталога людей.

    В макете каталог открывается не списком из ста человек, а перечнем
    специализаций: «Рабочий персонал», «ИТ и разработка», «Финансы».
    Человека ищут от того, что нужно сделать, а не от фамилии.
    """
    _name = 'coop.profession.category'
    _description = 'Категория специализаций'
    _order = 'name'

    name = fields.Char(string='Название', required=True, translate=False)
    profession_ids = fields.One2many(
        'coop.profession', 'category_id', string='Профессии')
    profession_count = fields.Integer(
        string='Профессий', compute='_compute_counts')
    partner_count = fields.Integer(
        string='Людей', compute='_compute_counts')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Такая категория уже есть.'),
    ]

    @api.depends('profession_ids.partner_count')
    def _compute_counts(self):
        for record in self:
            record.profession_count = len(record.profession_ids)
            record.partner_count = sum(record.profession_ids.mapped('partner_count'))


class CoopProfession(models.Model):
    """Профессия человека — то, кем он работает.

    Отдельно от навыков, и это не придирка. Профессия одна и отвечает на
    вопрос «кто это»; навыков много, и они отвечают на вопрос «что он
    возьмётся сделать». Сварщик, умеющий варить и класть кирпич, — это
    один сварщик с двумя навыками, а не два человека.
    """
    _name = 'coop.profession'
    _description = 'Профессия'
    _order = 'name'

    name = fields.Char(string='Название', required=True)
    category_id = fields.Many2one(
        'coop.profession.category', string='Категория',
        required=True, ondelete='restrict')
    partner_ids = fields.One2many(
        'res.partner', 'coop_profession_id', string='Люди')
    partner_count = fields.Integer(
        string='Людей', compute='_compute_partner_count', store=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Такая профессия уже есть.'),
    ]

    @api.depends('partner_ids.coop_is_participant')
    def _compute_partner_count(self):
        for record in self:
            record.partner_count = len(
                record.partner_ids.filtered('coop_is_participant'))
