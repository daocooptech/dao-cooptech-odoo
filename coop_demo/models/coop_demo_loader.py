# -*- coding: utf-8 -*-
from odoo import api, models

from ..data import emblems, load_org_profiles, load_orgs, load_people, load_reference


class CoopDemoLoader(models.AbstractModel):
    """Точка входа для наполнения каталогов из макета.

    Абстрактная модель, а не хук установки: хук выполняется только при
    установке, а данные каталогов нужно перезаливать и при обновлении
    модуля — иначе изменения в макете не доезжают до стенда, пока кто-то
    не пересоберёт базу с нуля.
    """
    _name = 'coop.demo.loader'
    _description = 'Загрузчик данных из макета'

    @api.model
    def load_all(self):
        # Порядок важен: справочник специализаций общий, и каталоги на
        # него ссылаются. Строить его внутри каждого загрузчика значит
        # получить два дерева, которые разойдутся при первой же правке.
        _categories, specializations = load_reference.load_specializations(self.env)
        load_people.load_people(self.env, specializations)
        # Один раздатчик знаков на весь прогон: иначе каталог и
        # заполненные карточки разберут одни и те же файлы дважды.
        marks = emblems.MarkAllocator()
        load_orgs.load_organizations(self.env, specializations, marks)
        load_org_profiles.load_org_profiles(self.env, specializations, marks)
        return True
