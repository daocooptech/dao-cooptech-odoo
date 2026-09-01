# -*- coding: utf-8 -*-
from odoo import api, models

from ..data import (emblems, load_bounty, load_org_profiles, load_orgs,
                    load_people, load_reference, load_resources, load_skills)


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
        # Ресурсы последними: им нужны владельцы, а владельцы — это
        # люди и организации, загруженные выше.
        load_resources.load_resources(self.env)
        load_skills.load_skills(self.env)
        # Задачи и токены последними: исполнителей берём из уже
        # загруженного каталога людей.
        load_bounty.load_bounty(self.env)
        return True
