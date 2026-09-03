# -*- coding: utf-8 -*-
from odoo import api, models

from ..data import (emblems, load_attributes, load_biography, load_bounty,
                    load_communities,
                    load_deals,
                    load_examples, load_memberships,
                    load_org_profiles, load_orgs, load_people, load_projects,
                    load_reference, load_resources, load_skills,
                    load_vacancies, load_verification, load_wallets)


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
        # Состав организаций — до каталогов: правила доступа смотрят на
        # полномочия в членстве, и объявления организаций должны попадать
        # к людям, которым эта организация поручила публикации.
        load_memberships.load_memberships(self.env)
        # Ресурсы последними: им нужны владельцы, а владельцы — это
        # люди и организации, загруженные выше.
        load_resources.load_resources(self.env)
        load_skills.load_skills(self.env)
        load_projects.load_projects(self.env)
        load_vacancies.load_vacancies(self.env)
        # Сообщества после каталогов: часть из них привязана к проектам,
        # а состав набирается из уже загруженных людей.
        load_communities.load_communities(self.env)
        # Характеристики после ресурсов: значения проставляются уже
        # заведённым объявлениям, и рубрики к этому моменту есть.
        load_attributes.load_attributes(self.env)
        # Биография после людей и членства: заполняется тем, кто уже
        # состоит на платформе.
        load_biography.load_biography(self.env)
        load_biography.age_listings(self.env)
        load_biography.add_followers(self.env)
        # Задачи и токены последними: исполнителей берём из уже
        # загруженного каталога людей.
        # Ступени верификации — после каталогов: загрузчик снимает с
        # публикации то, что по правилам разместить нельзя, и для этого
        # каталоги уже должны быть.
        load_verification.load_verification(self.env)
        # Сделки последними: у них предметом стоят записи каталогов, а
        # сторонами — участники со ступенями, и всё это должно уже быть.
        load_deals.load_deals(self.env)
        # Кошельки последними: состав вкладок зависит от членства, а
        # сальдо по контрагентам считается из платежей по сделкам.
        load_wallets.load_wallets(self.env)
        # Последним — добор примеров по случаям: он смотрит, чего в
        # данных не хватает, и потому должен видеть всё остальное.
        load_examples.load_examples(self.env)
        load_bounty.grant_admin_roles(self.env)
        load_bounty.load_bounty(self.env)
        return True
