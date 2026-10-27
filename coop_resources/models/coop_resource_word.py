# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoopResourceWord(models.Model):
    """Слово состава: сырьё или оборудование объявления.

    Решение владельца 26.10.2026: сырьё и оборудование — словами, а не
    связями с чужими объявлениями. Слово открывает каталог ресурсов
    поиском по нему в городе смотрящего — там видно, где взять сейчас.
    Справочник общий: «Вощина» у двух пасек — одно слово, и поиск по
    нему находит обе.
    """
    _name = 'coop.resource.word'
    _description = 'Слово состава ресурса'
    _order = 'name'

    name = fields.Char(string='Слово', required=True)

    _name_uniq = models.Constraint('unique(name)', 'Такое слово уже есть.')

    @api.model_create_multi
    def create(self, vals_list):
        # «вощина » и «Вощина» — одно слово: первая буква заглавная,
        # пробелы по краям срезаны. Иначе справочник распадается на
        # двойники, и поиск по слову находит половину.
        for vals in vals_list:
            name = (vals.get('name') or '').strip()
            vals['name'] = name[:1].upper() + name[1:]
        return super().create(vals_list)
