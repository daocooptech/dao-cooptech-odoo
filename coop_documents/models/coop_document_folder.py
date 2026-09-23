# -*- coding: utf-8 -*-
"""Папки документов — своя полка у каждого.

Владелец 23 сентября 2026: «надо сделать фильтры по документам и
возможность группировать их, может какие папки придумать?»

Папки и группировки — разные вещи, и нужны обе.

**Группировка отвечает на вопрос «покажи по виду».** Она считается от
самих записей: вид, вторая сторона, год, состояние. Её не надо заводить
и нельзя ошибиться — она всегда полная.

**Папка отвечает на вопрос «где я это держу».** Её заводит человек, и
она про его порядок, а не про свойства документа: «Стройка 2026»,
«Налоговая», «Спорные». Ни одна группировка такого не даст: платформа
не знает, что три документа связаны стройкой, пока человек не сказал.

Папка **личная**. Общая папка означала бы, что порядок у всех один, а
он у каждого свой: организатор закупки, бухгалтер кооператива и
участник раскладывают одни и те же документы по-разному.
"""
import re

from odoo import api, fields, models


class CoopDocumentFolder(models.Model):
    _name = 'coop.document.folder'
    _description = 'Папка документов'
    _parent_store = True
    _order = 'complete_name'

    name = fields.Char(string='Название', required=True)
    partner_id = fields.Many2one(
        'res.partner', string='Чья папка', required=True, index=True,
        ondelete='cascade',
        default=lambda self: self.env.user._coop_acting_partner())

    parent_id = fields.Many2one(
        'coop.document.folder', string='Внутри папки',
        index=True, ondelete='cascade')
    parent_path = fields.Char(index=True, unaccent=False)
    child_ids = fields.One2many(
        'coop.document.folder', 'parent_id', string='Вложенные')

    complete_name = fields.Char(
        string='Полный путь', compute='_compute_complete_name',
        store=True, recursive=True)

    document_ids = fields.One2many(
        'coop.document', 'folder_id', string='Документы')
    document_count = fields.Integer(
        string='Документов', compute='_compute_document_count')

    color = fields.Integer(string='Цвет')

    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('complete_name', 'partner_id.name', 'partner_id.is_company')
    def _compute_display_name(self):
        """Чья папка — видно в названии, если она не ваша личная.

        Человек действует и от себя, и от своих организаций, и папки у
        всех у них свои. Панель показывает их одним деревом, и без
        пометки выходит четыре «Закупки» подряд, неотличимые ничем.
        Проверено на боевой 23 сентября 2026: владелец видел по две
        папки каждого имени — свои и кооператива «Борозда».

        Свои папки остаются без приписки: она нужна там, где есть что
        различать, и мешает там, где нечего.
        """
        for record in self:
            path = record.complete_name or ''
            if not record.partner_id.is_company:
                record.display_name = path
                continue
            # Название впереди, чья — следом и коротко. Панель папок
            # узкая: с приписки начинать нельзя, она съедает ровно то,
            # ради чего человек в панель и смотрит. Проверено глазами на
            # боевой — с приписки спереди все папки читались как
            # «Кооператив «Борозда» ·».
            record.display_name = '%s · %s' % (
                path, self._short_owner(record.partner_id.name))

    @api.model
    def _short_owner(self, name):
        """Коротко о владельце: то, что в кавычках, либо первое слово.

        «Кооператив «Борозда»» → «Борозда», «ОАО «Вектор Инжиниринг»» →
        «Вектор Инжиниринг». Правовая форма в приписке не нужна: человек
        отличает свои организации по имени, а не по форме, и форма
        занимает место, которого в панели нет.
        """
        found = re.search(r'«([^»]+)»', name or '')
        if found:
            return found.group(1)
        return (name or '').split(',')[0].strip()

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for record in self:
            if record.parent_id:
                record.complete_name = '%s / %s' % (
                    record.parent_id.complete_name, record.name)
            else:
                record.complete_name = record.name

    def _compute_document_count(self):
        """Считаем вместе с вложенными.

        Папка «Стройка», внутри которой «Стройка / Акты», показывает
        сумму: иначе у верхней стоит ноль, и человек решает, что она
        пустая, хотя всё лежит на полку ниже.
        """
        counts = dict(self.env['coop.document']._read_group(
            [('folder_id', 'child_of', self.ids)],
            ['folder_id'], ['__count'])) if self.ids else {}
        by_id = {folder.id: count for folder, count in counts.items()}
        for record in self:
            inside = self.search([('id', 'child_of', record.id)])
            record.document_count = sum(by_id.get(i, 0) for i in inside.ids)

    _name_unique_in_parent = models.Constraint(
        'unique(partner_id, parent_id, name)',
        'Папка с таким названием у вас уже есть на этом уровне.',
    )
