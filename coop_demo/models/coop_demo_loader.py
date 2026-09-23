# -*- coding: utf-8 -*-
import logging

from odoo import api, models

from ..data import rubrics
from ..data import load_project_updates
from ..data import load_okved
from ..data import load_accounts
from ..data import (emblems, load_attributes, load_biography, load_bounty,
                    load_cessions,
                    load_tokens,
                    load_intangibles,
                    load_faces,
                    load_communities,
                    load_deals,
                    load_examples, load_memberships, load_messages,
                    load_org_profiles, load_orgs, load_people, load_projects,
                    load_auctions,
                    load_events,
                    load_groupbuy,
                    load_programs,
                    load_promotions,
                    load_reference, load_resources, load_skills,
                    load_project_needs, load_project_tasks,
                    load_photos,
                    load_documents,
                    load_notifications,
                    load_spread,
                    load_vacancies, load_verification, load_wallets,
                    load_warehouses)


_logger = logging.getLogger(__name__)

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
        # Лица: раздача и перестановка по полу одним проходом — двумя
        # они перебирали снимок заново на каждой выкатке.
        load_faces.ensure_faces(self.env)
        # Последним: дополняет то, чего не досталось витринной
        # странице при обычной раздаче.
        load_biography.enrich_showcase(self.env)
        # Образование — к справочнику заведений: записи заводились
        # свободной строкой, а показывать надо сокращение.
        load_biography.link_education(self.env)
        # Связи организаций — после членства: полка «Связанные
        # организации» на карточке иначе пуста у всех.
        load_orgs.link_organizations(self.env)
        # Услуги организациям: полка «Услуги» на карточке иначе не
        # появляется ни у одной.
        load_orgs.give_services(self.env)
        # Учётные записи участникам — после каталога людей и членства:
        # записи заводятся тем, кто уже состоит в организации или имеет
        # специализацию, а до загрузки каталогов таких попросту нет.
        #
        # Без этого шага вторая сторона любого взаимодействия не может
        # действовать: у сделки некому подтвердить акт, у вакансии —
        # ответить на отклик, у торга — перебить ставку.
        load_accounts.load_accounts(self.env)
        # Задачи и токены последними: исполнителей берём из уже
        # загруженного каталога людей.
        # Ступени верификации — после каталогов: загрузчик снимает с
        # публикации то, что по правилам разместить нельзя, и для этого
        # каталоги уже должны быть.
        load_verification.load_verification(self.env)
        # Сделки последними: у них предметом стоят записи каталогов, а
        # сторонами — участники со ступенями, и всё это должно уже быть.
        load_deals.load_deals(self.env)
        # Витрина уступок сразу за сделками и до кошельков: она возвращает
        # части завершённых сделок отсрочку по последнему платежу, а
        # сальдо по контрагентам считается как раз из платежей. Иначе
        # кошельки посчитались бы по данным, которые через шаг изменятся.
        if 'coop.cession' in self.env:
            load_cessions.load_cessions(self.env)
        # Биржа токенов после сделок и уступок: выпуски заводятся на
        # опубликованные объявления, а доли начисляются по уже принятым
        # вкладам в проекты — и то и другое к этому моменту уже есть.
        if 'coop.token.claim' in self.env:
            load_tokens.load_tokens(self.env)
        # Реестр НМА и заявки ЦФА — после проектов и токенов: активы
        # вносятся вкладом в проекты и получают доли по той же формуле,
        # что труд и техника, а значит механика долей должна уже работать.
        if 'coop.intangible' in self.env:
            load_intangibles.load_intangibles(self.env)
        # Продвижение — после объявлений и токенов: место занимается под
        # объявление и оплачивается токенами платформы.
        if 'coop.promotion' in self.env:
            load_promotions.load_promotions(self.env)
        # Целевые программы — после организаций и людей: организатор
        # программы всегда кооператив, участники — живые люди.
        if 'coop.program' in self.env:
            load_programs.load_programs(self.env)
        # Совместные закупки — после организаций: организатор всегда
        # кооператив, заказчики — участники.
        if 'coop.groupbuy' in self.env:
            load_groupbuy.load_groupbuy(self.env)
        # События — после сообществ: часть событий проводят они.
        if 'coop.event' in self.env:
            load_events.load_events(self.env)
        # Потребности — после сделок и до задач: они объявляются на
        # этапе сбора, и предложения на них становятся вкладами.
        if 'coop.resource' in self.env:
            load_project_needs.load_project_needs(self.env)
            # Разброс по всем четырём видам — после общего наполнения:
            # тот шаг заводит первую потребность проекта, этот доводит
            # число потребностей до правдоподобного и закрывает виды
            # (труд и деньги), которых не бывает у первого шага.
            load_project_needs.diversify_project_needs(self.env)
        # Задачи проектов — после того, как сборы вкладов обзавелись
        # проектами в управлении: задача заводится в управляемом проекте,
        # а исполнители берутся из вкладчиков сбора.
        if 'project.task' in self.env:
            load_project_tasks.load_project_tasks(self.env)
        # Склады и биржа мощностей — после сделок: сданное другим место
        # склад считает по действующим договорённостям, а не по
        # введённому числу, и договорённости для этого должны уже быть.
        if 'coop.warehouse' in self.env:
            load_warehouses.load_warehouses(self.env)
        # Аукционы — после ресурсов: лот часто ссылается на объявление.
        if 'coop.auction' in self.env:
            load_auctions.load_auctions(self.env)
        # Кошельки последними: состав вкладок зависит от членства, а
        # сальдо по контрагентам считается из платежей по сделкам.
        load_wallets.load_wallets(self.env)
        # Последним — добор примеров по случаям: он смотрит, чего в
        # данных не хватает, и потому должен видеть всё остальное.
        load_examples.load_examples(self.env)
        load_bounty.grant_admin_roles(self.env)
        load_bounty.load_bounty(self.env)
        # Переписки в самом конце: они заводятся вокруг сделок,
        # проектов, сообществ и организаций, и до их появления
        # разговаривать не о чем.
        load_messages.load_messages(self.env)
        # Снимки последними и по всем каталогам разом.
        #
        # Отдельным проходом, а не внутри каждого загрузчика: каталоги
        # наполнялись в разное время и разными людьми, и часть из них
        # снимок не ставила вовсе — сделки, аукционы, реестр НМА,
        # складчина. Владелец 15 сентября 2026: «во всех каталогах
        # должны быть картинки». Проход идёт по тем записям, у которых
        # снимка нет, и потому безвреден при повторном запуске.
        # Отчёты о ходе — после задач и сборов: состояние отчёта
        # выводится из положения проекта, и положение к этому моменту
        # должно быть окончательным.
        if 'project.update' in self.env:
            load_project_updates.load_project_updates(self.env)
        # Суммы проектов — до всего остального, что на них смотрит:
        # готовность, доли и вехи считаются от «нужно».
        load_projects.repair_scales(self.env)
        # Вехи — после сумм: их названия содержат сами суммы.
        if 'project.milestone' in self.env:
            self.env['coop.project'].sudo().backfill_milestones()
        # Вид деятельности организаций — по названию и правовой форме.
        if 'coop.okved' in self.env:
            load_okved.load_okved(self.env)
        # Рубрики — до снимков: и то и другое выводится из названия, но
        # рубрика ещё и решает, в какой полке запись окажется.
        self._load_rubrics()
        # Выравнивание полок на страницах людей — до снимков: оно заводит
        # личные потребности, и снимок им нужен такой же, как всем.
        load_memberships.trim_memberships(self.env)
        load_spread.spread_all(self.env)
        # Город — до снимков и по всем участникам разом. Город карточки
        # ресурса, права и объявления берётся у хозяина, а не у записи:
        # у нематериальных прав это прямо `related='owner_id.city'`.
        # Шесть прав из пятисот двадцати стояли в каталоге без места
        # именно поэтому — чинить надо было не каталог, а карточку
        # правообладателя.
        load_people.ensure_cities(self.env)
        # Снимки — последним шагом и одним проходом по всем каталогам:
        # раздача только в пустые поля оставляла записи с тем, что им
        # досталось при первом прогоне, и правка правила до них не
        # доезжала никогда.
        load_photos.ensure_photos(self.env)
        # Извещения — самым последним: они порождаются из того, что уже
        # произошло, и до того, как события заведены, порождать их не из
        # чего (решение 375).
        load_documents.load_documents(self.env)
        load_notifications.load_notifications(self.env)
        # Знаки организаций — тем же порядком: набор эмблем чистили от
        # того, что знаком не было, и у карточек это осталось стоять.
        load_photos.ensure_marks(self.env)
        return True

    def _load_rubrics(self):
        """Проставить рубрику тем, у кого её нет.

        Отдельным проходом, а не внутри загрузчика потребностей: тот
        пропускает проекты, у которых потребности уже есть, и до старых
        записей никогда не доходит. Владелец увидел это на витрине —
        в полке «Другое» лежала треть каталога.
        """
        # Двойники — до наполнения: иначе часть записей уедет в рубрику,
        # которую через шаг удалим.
        merged = rubrics.merge_duplicate_categories(self.env)
        if merged:
            _logger.info('Рубрики: сведено двойников %s', merged)
        placed, missed = rubrics.fill_resources(self.env)
        if placed or missed:
            _logger.info('Ресурсы: рубрика проставлена %s, не выведена %s',
                         placed, missed)
        placed, missed = rubrics.fill_vacancies(self.env)
        if placed or missed:
            _logger.info('Вакансии: специализация проставлена %s, '
                         'не выведена %s', placed, missed)

