# -*- coding: utf-8 -*-
"""Снимок по роду занятий — для вакансий и предложений навыка.

Зачем отдельно от правил по названию. Правила в `load_resources`
отвечают на вопрос «что это за предмет»: цемент, бетономешалка, сено.
У вакансии предмета нет — есть занятие, и снимок ей нужен другой: не
сварочный аппарат, а сварщик за работой.

Откуда взялась беда. Снимок вакансии и навыка брался из макета — из
поля `photo` в `vacancies.json` и `skills.json`. В макете он проставлен
наугад: у «Швеи» стояла сварка, у «Повара» — столярный цех, у
«Пчеловода» — деловая встреча. Владелец 20 сентября 2026: «пробеги по
всем каталогам, посмотри чтобы картинки совпадали».

Как теперь. Снимок берётся по специализации записи — по тому самому
справочнику, по которому каталог группирует и фильтрует. У каждой
специализации несколько снимков, и какой из них достанется записи,
решает её название: тогда двести вакансий сварщика не выглядят одной
размноженной карточкой, но одна и та же вакансия не меняет вид от
прогона к прогону.

Снимки лежат в трёх папках: `vacancies` и `skills` сняты под занятия,
`resources` — под предметы, и оттуда берётся то, чего в первых двух не
было вовсе (охранник, переводчик, массажист, кассовый прилавок).
"""
import base64
import os
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img')

# Специализация → снимки, «папка/файл». Порядок внутри значения не
# важен: какой достанется записи, решает её название.
СНИМКИ = {
    'HR-менеджер': ('vacancies/business-meeting.jpg', 'vacancies/coworking.jpg',
                    'skills/office-desk.jpg'),
    'SMM': ('vacancies/smm-specialist.jpg', 'skills/marketer.jpg',
            'resources/ui-design.jpg'),
    'Автосервис, автомойка': ('skills/car-mechanic.jpg',
                              'vacancies/car-mechanic.jpg'),
    'Автослесарь, автомеханик': ('vacancies/car-mechanic.jpg',
                                 'skills/car-mechanic.jpg'),
    'Агент по недвижимости': ('vacancies/house-manager.jpg',
                              'vacancies/hotel-administrator.jpg',
                              'skills/office-desk.jpg'),
    'Агроном, зоотехник': ('vacancies/greenhouse-lettuce.jpg',
                           'skills/greenhouse-interior.jpg',
                           'vacancies/greenhouse.jpg',
                           'resources/vegetable-field.jpg'),
    'Административный директор': ('vacancies/coworking.jpg',
                                  'skills/office-desk.jpg',
                                  'vacancies/business-meeting.jpg'),
    'Администратор гостиницы': ('vacancies/hotel-administrator.jpg',
                                'vacancies/house-manager.jpg'),
    'Аналитика, Data Science': ('resources/data-analytics.jpg',
                                'vacancies/laptop-desk.jpg',
                                'vacancies/open-source-crm.jpg'),
    'Архитектор': ('resources/blueprint.jpg', 'vacancies/modular-house.jpg',
                   'vacancies/pedestrian-bridge.jpg'),
    'Бетонщик, арматурщик, каменщик': ('vacancies/bricklayer-house.jpg',
                                       'skills/mason.jpg', 'skills/mason-2.jpg',
                                       'skills/brick-stack.jpg'),
    'Бизнес-консультант': ('vacancies/business-meeting.jpg',
                           'vacancies/grant-manager.jpg',
                           'skills/office-desk.jpg'),
    'Бухгалтерия': ('vacancies/accountant-office.jpg', 'skills/accountant.jpg'),
    'Ветеринар': ('vacancies/mobile-clinic.jpg', 'skills/mobile-clinic.jpg',
                  'vacancies/doctor-gp.jpg'),
    'Водитель': ('vacancies/delivery-driver.jpg', 'vacancies/van-transfer.jpg',
                 'skills/delivery-van.jpg'),
    'Врач': ('vacancies/doctor-gp.jpg', 'vacancies/mobile-clinic.jpg',
             'resources/nurse.jpg'),
    'Горный инженер': ('vacancies/construction-foreman.jpg',
                       'skills/excavator-work.jpg', 'skills/excavator.jpg'),
    'Дизайн, графика': ('vacancies/web-designer.jpg', 'skills/web-designer.jpg',
                        'resources/ui-design.jpg', 'resources/brand-design.jpg'),
    'Дизайнер, художник': ('skills/interior-designer.jpg',
                           'vacancies/web-designer.jpg', 'skills/engraver.jpg'),
    'Диспетчер': ('vacancies/logistics-dispatcher.jpg',
                  'vacancies/grid-dispatcher.jpg', 'resources/call-center.jpg'),
    'Домработница, няня': ('vacancies/house-manager.jpg',
                           'vacancies/laundromat.jpg'),
    'Журналистика, СМИ': ('resources/editing-desk.jpg',
                          'vacancies/videographer.jpg',
                          'vacancies/photographer.jpg'),
    'Инженер строительного контроля': ('vacancies/construction-foreman.jpg',
                                       'resources/site-supervisor.jpg',
                                       'vacancies/scaffolding.jpg'),
    'Инженер-технолог': ('vacancies/plastics-technologist.jpg',
                         'skills/craft-workshop.jpg',
                         'resources/factory-operator.jpg'),
    'Кассир': ('vacancies/cashier.jpg', 'resources/shop-counter.jpg'),
    'Кладовщик, Приемщик товаров': ('vacancies/warehouse-worker.jpg',
                                    'resources/warehouse-shelves.jpg'),
    'Кредитный специалист': ('vacancies/credit-specialist.jpg',
                             'resources/bank-office.jpg',
                             'vacancies/grant-manager.jpg'),
    'Логистика, ВЭД': ('skills/logistician.jpg',
                       'vacancies/logistics-dispatcher.jpg',
                       'vacancies/delivery-driver.jpg'),
    'Маркетинг': ('skills/marketer.jpg', 'vacancies/smm-specialist.jpg',
                  'vacancies/business-meeting.jpg'),
    'Массажист, косметолог': ('resources/massage.jpg',
                              'vacancies/sports-coach.jpg'),
    'Медсестра, фельдшер': ('vacancies/nurse-mobile-clinic.jpg',
                            'resources/nurse.jpg', 'vacancies/mobile-clinic.jpg'),
    'Менеджер по закупкам': ('vacancies/business-meeting.jpg',
                             'skills/office-desk.jpg',
                             'resources/warehouse-shelves.jpg'),
    'Менеджер по продажам': ('vacancies/farm-seller.jpg',
                             'resources/shop-counter.jpg',
                             'vacancies/business-meeting.jpg'),
    'Народные промыслы, ремёсла': ('skills/craft-workshop.jpg',
                                   'vacancies/woodcarver.jpg',
                                   'skills/pottery-wheel.jpg',
                                   'skills/weaving-loom.jpg'),
    'Офис-менеджер, ассистент': ('skills/office-desk.jpg',
                                 'vacancies/coworking.jpg'),
    'Охранник, контролёр': ('resources/security-guard.jpg',),
    'Переводчик': ('resources/translator-desk.jpg', 'resources/editing-desk.jpg'),
    'Повар, кондитер': ('vacancies/baker-pastry.jpg', 'skills/pastry-chef.jpg',
                        'resources/confectioner.jpg'),
    'Преподаватель, репетитор': ('vacancies/coding-class.jpg',
                                 'resources/workshop-class.jpg',
                                 'vacancies/woodwork-mentor.jpg'),
    'Программирование, Разработка': ('vacancies/programmer.jpg',
                                     'vacancies/programmer-desk.jpg',
                                     'skills/programmer.jpg',
                                     'resources/code-review.jpg'),
    'Продавец': ('resources/shop-counter.jpg', 'vacancies/farm-seller.jpg',
                 'vacancies/cashier.jpg'),
    'Прораб, мастер СМР': ('vacancies/construction-foreman.jpg',
                           'resources/site-supervisor.jpg',
                           'vacancies/building-renovation.jpg'),
    'Пчеловодство, животноводство': ('vacancies/beekeeper-apiary.jpg',
                                     'skills/beekeeper.jpg',
                                     'resources/beekeeper-work.jpg',
                                     'skills/sheep-flock.jpg'),
    'Разное': ('skills/craft-workshop.jpg', 'vacancies/makerspace.jpg'),
    'Разнорабочий': ('vacancies/general-laborer.jpg',
                     'resources/workwear-ppe.jpg', 'vacancies/scaffolding.jpg'),
    'Руководитель проектов': ('vacancies/business-meeting.jpg',
                              'vacancies/grant-manager.jpg',
                              'skills/office-desk.jpg'),
    'Сварщик': ('vacancies/welder-argon.jpg', 'skills/welder.jpg',
                'skills/welding-work.jpg', 'skills/welding-machine.jpg'),
    'Слесарь, сантехник': ('vacancies/plumber-pipes.jpg', 'skills/plumber.jpg',
                           'skills/car-mechanic.jpg'),
    'Столяр, плотник': ('skills/carpenter.jpg',
                        'vacancies/carpenter-workshop.jpg',
                        'skills/carpentry-shop.jpg',
                        'vacancies/woodwork-mentor.jpg'),
    'Тестирование': ('resources/code-review.jpg',
                     'vacancies/programmer-desk.jpg'),
    'Тракторист': ('vacancies/tractor-driver.jpg', 'skills/tractor-field.jpg',
                   'skills/mini-tractor.jpg'),
    'Тренер': ('vacancies/sports-coach.jpg', 'vacancies/climbing-gym.jpg'),
    'Флорист, декоратор': ('skills/florist.jpg', 'skills/interior-designer.jpg'),
    'Фото, видео, звукооператоры': ('vacancies/photographer.jpg',
                                    'skills/photographer.jpg',
                                    'vacancies/videographer.jpg',
                                    'resources/camera-rig.jpg'),
    'Швея, закройщик': ('vacancies/seamstress-sewing.jpg',
                        'skills/seamstress.jpg',
                        'resources/sewing-machine.jpg'),
    'Электромонтажник, электромонтер, техник-электрик': (
        'vacancies/electrician.jpg', 'skills/electrician.jpg',
        'resources/electrician-work.jpg'),
    'Юрисконсульт': ('vacancies/lawyer.jpg', 'skills/lawyer.jpg',
                     'vacancies/junior-lawyer.jpg', 'resources/law-books.jpg'),
}


def файлы(specialization):
    """Снимки, годные этой специализации, — только те, что есть на диске."""
    пути = СНИМКИ.get(specialization or '', ())
    return [п for п in пути if os.path.exists(os.path.join(IMG_DIR, п))]


def photo_for(name, specialization):
    """Снимок по роду занятий, готовый к записи в поле, или пусто.

    Выбор по названию, а не наугад: у одной и той же записи снимок
    должен быть один и тот же при каждом прогоне, иначе каталог меняется
    на ровном месте и отличить правку от шума нельзя.
    """
    годные = файлы(specialization)
    if not годные:
        return None
    номер = zlib.crc32((name or '').encode('utf-8')) % len(годные)
    with open(os.path.join(IMG_DIR, годные[номер]), 'rb') as fh:
        return base64.b64encode(fh.read())


def все_файлы():
    """Все снимки занятий — по ним узнаётся раздача в базе."""
    пути = set()
    for значения in СНИМКИ.values():
        пути.update(значения)
    return sorted(пути)
