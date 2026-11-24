# -*- coding: utf-8 -*-
"""Вакансии и навыки: поля по профессии (№ 483, 24.11.2026).

Набор висит на специализации и общий у вакансии и навыка. Специализации
вакансий раньше стояли жребием («Кузнец» в «Медсестре») — сперва они
раскладываются по названию, иначе поля профессии не имели бы смысла.
"""
import logging
import random
import re

from .load_attributes import _slug
from .load_branch_attributes import _ensure_options

_logger = logging.getLogger(__name__)

# Каких специализаций не хватало под профессии Авито, что есть в каталоге.
NEW_SPECS = [
    ('Отделочник, кровельщик, печник', 'Строительство, недвижимость'),
    ('Оператор оборудования', 'Производство, сервисное обслуживание'),
    ('Кузнец, литейщик', 'Производство, сервисное обслуживание'),
    ('Сыродел, мастер переработки', 'Производство, сервисное обслуживание'),
]

# Название → специализация; первое совпадение. Порядок важен: «Методист по
# бухгалтерскому учёту» — бухгалтерия, «Ветеринарный фельдшер» — ветеринар.
BY_TITLE = [
    (r'автослесарь|автомеханик', 'Автослесарь, автомеханик'),
    (r'прораб', 'Прораб, мастер СМР'),
    (r'координатор волонтёров', 'HR-менеджер'),
    (r'наставник', 'Преподаватель, репетитор'),
    (r'энергоаудитор|по эксплуатации|дежурный инженер|ветроустанов', 'Инженер-технолог'),
    (r'3d-принтер|лесопильн|3d-печат', 'Оператор оборудования'),
    (r'садовод', 'Агроном, зоотехник'),
    (r'ремонту техники', 'Слесарь, сантехник'),
    (r'разбора заявок|оповещения', 'Руководитель проектов'),
    (r'внедренец', 'Программирование, Разработка'),
    (r'библиотекар', 'Разное'),
    (r'ветеринар', 'Ветеринар'),
    (r'сыровар|сыродел', 'Сыродел, мастер переработки'),
    (r'скотник|доярк|пасечник|пчеловод|на пасеку', 'Пчеловодство, животноводство'),
    (r'агроном|зоотехник', 'Агроном, зоотехник'),
    (r'тракторист', 'Тракторист'),
    (r'кузнец|литейщик', 'Кузнец, литейщик'),
    (r'печник|кровельщик|отделочник|штукатур|маляр|плиточник',
     'Отделочник, кровельщик, печник'),
    (r'оператор (сушильн|пилорам|дробилк|доильн|сортировк|печатн|общественной прач)'
     r'|крановщик', 'Оператор оборудования'),
    (r'электромонт|электрик|солнечных панел', 'Электромонтажник, электромонтер, техник-электрик'),
    (r'сварщик', 'Сварщик'),
    (r'слесарь|сантехник', 'Слесарь, сантехник'),
    (r'плотник|столяр|краснодерев', 'Столяр, плотник'),
    (r'каменщик|бетонщик|арматурщик', 'Бетонщик, арматурщик, каменщик'),
    (r'пекарь|повар|кондитер', 'Повар, кондитер'),
    (r'швея|закройщик', 'Швея, закройщик'),
    (r'гончар|резчик|реставратор', 'Народные промыслы, ремёсла'),
    (r'водитель', 'Водитель'),
    (r'кладовщик|приёмщик|пункта выдачи', 'Кладовщик, Приемщик товаров'),
    (r'бухгалтер|учётной систем', 'Бухгалтерия'),
    (r'логист', 'Логистика, ВЭД'),
    (r'диспетчер', 'Диспетчер'),
    (r'менеджер по закупкам', 'Менеджер по закупкам'),
    (r'менеджер по продажам', 'Менеджер по продажам'),
    (r'smm', 'SMM'),
    (r'юрист|юрисконсульт|юридическ', 'Юрисконсульт'),
    (r'медсестра', 'Медсестра, фельдшер'),
    (r'врач', 'Врач'),
    (r'тестировщик|аудитор смарт|проверка протокола|попыток подбора', 'Тестирование'),
    (r'ux-|дизайнер интерфейс', 'Дизайн, графика'),
    (r'разработчик|ревизия кода|программист', 'Программирование, Разработка'),
    (r'видеосъ|фотограф|видеооператор', 'Фото, видео, звукооператоры'),
    (r'редактор|технический писатель|журналист', 'Журналистика, СМИ'),
    (r'переводчик', 'Переводчик'),
    (r'тренер', 'Тренер'),
    (r'преподаватель|репетитор|куратор образоват|методист', 'Преподаватель, репетитор'),
    (r'проектировщик|архитектор', 'Архитектор'),
    (r'технолог|технических условий|лабораторн', 'Инженер-технолог'),
    (r'разнорабоч|волонтёр', 'Разнорабочий'),
    (r'консультант|консультация|грант', 'Бизнес-консультант'),
    (r'секретарь', 'Офис-менеджер, ассистент'),
]

# код, название, тип, единица, вид фильтра, варианты
ATTRS = [
    ('w_licence', 'Категория прав', 'tags', False, 'checkbox',
     ['B', 'BE', 'C', 'CE', 'D', 'M', 'Тракторные (Гостехнадзор)']),
    ('w_vehicle', 'Транспорт', 'tags', False, 'checkbox',
     ['Легковой', 'Лёгкий коммерческий', 'Грузовой до 10 т', 'Фура', 'Автобус',
      'Спецтехника']),
    ('w_route', 'Маршруты', 'selection', False, 'checkbox',
     ['По городу', 'По области', 'Междугородние', 'Международные']),
    ('w_own_car', 'Свой транспорт', 'boolean', False, 'switch', []),
    ('w_tacho', 'Карта тахографа', 'boolean', False, 'switch', []),
    ('w_adr', 'Допуск к опасным грузам', 'boolean', False, 'switch', []),
    ('w_machine', 'Техника', 'tags', False, 'checkbox',
     ['МТЗ', 'Мини-трактор', 'Комбайн', 'Погрузчик', 'Экскаватор', 'Косилка']),
    ('w_weld', 'Виды сварки', 'tags', False, 'checkbox',
     ['Ручная дуговая (MMA)', 'Полуавтомат (MIG/MAG)', 'Аргон (TIG)', 'Газовая',
      'Контактная']),
    ('w_metal', 'Материал', 'tags', False, 'checkbox',
     ['Чёрный металл', 'Нержавейка', 'Алюминий', 'Трубы']),
    ('w_naks', 'Аттестация НАКС', 'boolean', False, 'switch', []),
    ('w_grade', 'Разряд', 'integer', False, 'checkbox', []),
    ('w_el_group', 'Группа по электробезопасности', 'selection', False, 'checkbox',
     ['II', 'III', 'IV', 'V']),
    ('w_voltage', 'Напряжение', 'selection', False, 'checkbox',
     ['До 1000 В', 'До и выше 1000 В']),
    ('w_el_works', 'Виды работ', 'tags', False, 'checkbox',
     ['Проводка', 'Щиты', 'Освещение', 'Слаботочные сети', 'Солнечные панели',
      'Промышленное оборудование']),
    ('w_height', 'Допуск к работам на высоте', 'boolean', False, 'switch', []),
    ('w_own_tool', 'Свой инструмент', 'boolean', False, 'switch', []),
    ('w_build', 'Виды работ', 'tags', False, 'checkbox',
     ['Бетон', 'Арматура', 'Кирпичная кладка', 'Газоблок', 'Фундамент', 'Стяжка']),
    ('w_finish', 'Виды работ', 'tags', False, 'checkbox',
     ['Штукатурка', 'Покраска', 'Плитка', 'Гипсокартон', 'Полы', 'Кровля', 'Фасад',
      'Печи и камины']),
    ('w_wood', 'Виды работ', 'tags', False, 'checkbox',
     ['Срубы', 'Каркасные дома', 'Мебель', 'Лестницы', 'Окна и двери', 'Террасы']),
    ('w_wood_kind', 'Порода', 'tags', False, 'checkbox',
     ['Сосна', 'Лиственница', 'Дуб', 'Берёза', 'Фанера и МДФ']),
    ('w_plumb', 'Виды работ', 'tags', False, 'checkbox',
     ['Водоснабжение', 'Отопление', 'Канализация', 'Ремонт оборудования',
      'Сборка узлов']),
    ('w_operator', 'Оборудование', 'tags', False, 'checkbox',
     ['Пилорама', 'Сушильный комплекс', 'Дробилка и пресс', 'Доильный зал',
      'Сортировочная линия', 'Печатная установка', 'Портальный кран', 'Прачечная']),
    ('w_forge', 'Виды работ', 'tags', False, 'checkbox',
     ['Художественная ковка', 'Инструмент', 'Ограды и решётки', 'Литьё']),
    ('w_dairy', 'Продукт', 'tags', False, 'checkbox',
     ['Мягкие сыры', 'Твёрдые сыры', 'Творог и кисломолочное', 'Мясная переработка']),
    ('w_cuisine', 'Кухня', 'tags', False, 'checkbox',
     ['Русская', 'Европейская', 'Кавказская', 'Азиатская', 'Выпечка и хлеб',
      'Десерты']),
    ('w_kitchen_place', 'Участок', 'selection', False, 'checkbox',
     ['Горячий цех', 'Холодный цех', 'Кондитерский цех', 'Пекарня', 'Универсал']),
    ('w_medbook', 'Медицинская книжка', 'boolean', False, 'switch', []),
    ('w_sewing', 'Изделия', 'tags', False, 'checkbox',
     ['Спецодежда', 'Верхняя одежда', 'Платья и блузы', 'Трикотаж', 'Домашний текстиль',
      'Кожа']),
    ('w_sew_machine', 'Машины', 'tags', False, 'checkbox',
     ['Прямострочная', 'Оверлок', 'Плоскошовная', 'Вышивальная']),
    ('w_animals', 'Животные', 'tags', False, 'checkbox',
     ['Коровы', 'Козы и овцы', 'Свиньи', 'Птица', 'Лошади', 'Пчёлы', 'Домашние питомцы']),
    ('w_crops', 'Культуры', 'tags', False, 'checkbox',
     ['Зерновые', 'Овощи', 'Сады и ягоды', 'Теплицы', 'Кормовые травы']),
    ('w_stack', 'Языки и технологии', 'tags', False, 'checkbox',
     ['Python', 'JavaScript', 'TypeScript', 'Java', 'C#', 'PHP', 'Go', 'SQL', '1С',
      'Solidity']),
    ('w_dev_role', 'Направление', 'selection', False, 'checkbox',
     ['Бэкенд', 'Фронтенд', 'Полный стек', 'Мобильная разработка', 'Интеграции',
      'Смарт-контракты']),
    ('w_level', 'Уровень', 'selection', False, 'checkbox',
     ['Начинающий', 'Средний', 'Старший', 'Ведущий']),
    ('w_test', 'Вид проверки', 'tags', False, 'checkbox',
     ['Ручная', 'Автотесты', 'Нагрузочная', 'Безопасность', 'Аудит кода']),
    ('w_design', 'Направление', 'tags', False, 'checkbox',
     ['Интерфейсы', 'Фирменный стиль', 'Полиграфия', 'Иллюстрация', 'Интерьеры',
      'Ландшафт']),
    ('w_soft', 'Программы', 'tags', False, 'checkbox',
     ['Figma', 'Photoshop', 'Illustrator', 'Blender', 'AutoCAD', 'Revit', 'ArchiCAD']),
    ('w_portfolio', 'Есть портфолио', 'boolean', False, 'switch', []),
    ('w_acc_area', 'Участок учёта', 'tags', False, 'checkbox',
     ['Первичка', 'Зарплата', 'Банк и касса', 'Налоги и отчётность', 'Склад',
      'Весь учёт']),
    ('w_tax', 'Налоговый режим', 'tags', False, 'checkbox',
     ['ОСНО', 'УСН', 'ЕСХН', 'Патент', 'АУСН']),
    ('w_acc_soft', 'Программы учёта', 'tags', False, 'checkbox',
     ['1С:Бухгалтерия', 'Контур', 'СБИС', 'Odoo', 'МойСклад']),
    ('w_law', 'Отрасль права', 'tags', False, 'checkbox',
     ['Договоры', 'Корпоративное и кооперативы', 'Трудовое', 'Земельное', 'Налоговое',
      'Суды', 'Интеллектуальная собственность']),
    ('w_advocate', 'Статус адвоката', 'boolean', False, 'switch', []),
    ('w_med_spec', 'Направление', 'selection', False, 'checkbox',
     ['Общая практика', 'Педиатрия', 'Терапия', 'Процедурная', 'Выездная бригада',
      'Реабилитация']),
    ('w_accred', 'Аккредитация', 'boolean', False, 'switch', []),
    ('w_subject', 'Предмет', 'tags', False, 'checkbox',
     ['Математика', 'Русский язык', 'Иностранный язык', 'Информатика',
      'Экономика и кооперация', 'Ремёсла', 'Начальная школа']),
    ('w_pupils', 'Кого учит', 'tags', False, 'checkbox',
     ['Дошкольники', 'Школьники', 'Студенты', 'Взрослые']),
    ('w_languages', 'Языки', 'tags', False, 'checkbox',
     ['Английский', 'Немецкий', 'Китайский', 'Турецкий', 'Казахский', 'Якутский',
      'Татарский']),
    ('w_translate', 'Вид перевода', 'selection', False, 'checkbox',
     ['Письменный', 'Устный последовательный', 'Синхронный', 'Локализация']),
    ('w_sport', 'Вид занятий', 'tags', False, 'checkbox',
     ['Фитнес', 'Воркаут', 'Йога', 'Единоборства', 'Плавание', 'Детский спорт']),
    ('w_shoot', 'Что снимает', 'tags', False, 'checkbox',
     ['Портреты и семья', 'События', 'Предметная съёмка', 'Видео', 'Монтаж', 'Съёмка с дрона',
      'Звук']),
    ('w_own_gear', 'Своя техника', 'boolean', False, 'switch', []),
    ('w_text', 'Вид работы', 'tags', False, 'checkbox',
     ['Статьи', 'Редактура', 'Техническая документация', 'Новости', 'Сценарии']),
    ('w_craft', 'Ремесло', 'tags', False, 'checkbox',
     ['Гончарное дело', 'Резьба по дереву', 'Камень', 'Ткачество', 'Роспись', 'Гравировка']),
    ('w_store', 'Чем занимается', 'tags', False, 'checkbox',
     ['Приёмка', 'Отгрузка', 'Инвентаризация', 'Комплектация', 'Выдача заказов']),
    ('w_store_soft', 'Учётные программы', 'tags', False, 'checkbox',
     ['1С:Склад', 'МойСклад', 'Odoo', 'Терминал сбора данных']),
    ('w_forklift', 'Права на погрузчик', 'boolean', False, 'switch', []),
    ('w_trade', 'Что продаёт', 'tags', False, 'checkbox',
     ['Продукты', 'Одежда', 'Стройматериалы', 'Техника', 'Услуги', 'Оптом']),
    ('w_cash', 'Опыт работы на кассе', 'boolean', False, 'switch', []),
    ('w_crm', 'Опыт работы в CRM', 'boolean', False, 'switch', []),
    ('w_logist', 'Направление', 'tags', False, 'checkbox',
     ['Городская доставка', 'Междугородние перевозки', 'Международные перевозки',
      'Таможня', 'Складская логистика']),
    ('w_market', 'Каналы', 'tags', False, 'checkbox',
     ['VK', 'Telegram', 'Директ', 'SEO', 'Почтовые рассылки', 'Маркетплейсы']),
    ('w_consult', 'Тема', 'tags', False, 'checkbox',
     ['Кооперация', 'Финансы', 'Гранты', 'Стратегия', 'Управление', 'Кадры']),
    ('w_build_object', 'Объекты', 'tags', False, 'checkbox',
     ['Частные дома', 'Многоквартирные дома', 'Промышленные', 'Дороги и сети',
      'Общественные здания']),
    ('w_norm', 'В национальном реестре специалистов', 'boolean', False, 'switch', []),
    ('w_tech_area', 'Производство', 'selection', False, 'checkbox',
     ['Пищевое', 'Металлообработка', 'Деревообработка', 'Швейное', 'Химическое',
      'Горное дело']),
    ('w_auto', 'Виды работ', 'tags', False, 'checkbox',
     ['Двигатель', 'Ходовая', 'Электрика', 'Кузов и покраска', 'Шиномонтаж', 'Мойка']),
    ('w_labour', 'Виды работ', 'tags', False, 'checkbox',
     ['Погрузка и разгрузка', 'Уборка территории', 'Земляные работы',
      'Подсобные на стройке', 'Сортировка и упаковка', 'Сбор урожая']),
    ('w_security', 'Удостоверение охранника', 'selection', False, 'checkbox',
     ['Нет', '4 разряд', '5 разряд', '6 разряд']),
    ('w_beauty', 'Услуги', 'tags', False, 'checkbox',
     ['Классический массаж', 'Лечебный массаж', 'Уход за лицом', 'Эпиляция']),
    ('w_home', 'Чем занимается', 'tags', False, 'checkbox',
     ['Уборка', 'Готовка', 'Уход за детьми', 'Уход за пожилыми', 'Глажка']),
    ('w_office', 'Чем занимается', 'tags', False, 'checkbox',
     ['Документооборот', 'Приём звонков', 'Протоколы собраний', 'Кадровый учёт',
      'Закупки для офиса']),
    ('w_hotel', 'Чем занимается', 'tags', False, 'checkbox',
     ['Приём гостей', 'Бронирование', 'Касса', 'Ночные смены']),
    ('w_floral', 'Виды работ', 'tags', False, 'checkbox',
     ['Букеты', 'Оформление событий', 'Фитодизайн', 'Озеленение']),
    ('w_estate', 'Объекты', 'tags', False, 'checkbox',
     ['Квартиры', 'Дома и участки', 'Коммерческая', 'Аренда']),
    ('w_lead', 'Размер команды, человек', 'integer', False, 'range', []),
    ('w_data', 'Инструменты', 'tags', False, 'checkbox',
     ['SQL', 'Python', 'Excel', 'Power BI', 'Статистика', 'Машинное обучение']),
    ('w_credit', 'Виды займов', 'tags', False, 'checkbox',
     ['Потребительские', 'Бизнесу', 'Ипотека', 'Займы пайщикам']),
    ('w_supply', 'Что закупает', 'tags', False, 'checkbox',
     ['Сырьё', 'Оборудование', 'Продукты', 'Стройматериалы', 'Канцелярия']),
]

SETS = {
    'Водитель': 'w_licence w_vehicle w_route w_own_car w_tacho w_adr',
    'Тракторист': 'w_licence w_machine w_grade',
    'Сварщик': 'w_weld w_metal w_grade w_naks w_height w_own_tool',
    'Электромонтажник, электромонтер, техник-электрик':
        'w_el_works w_el_group w_voltage w_grade w_height w_own_tool',
    'Бетонщик, арматурщик, каменщик': 'w_build w_grade w_height w_own_tool',
    'Отделочник, кровельщик, печник': 'w_finish w_grade w_height w_own_tool',
    'Столяр, плотник': 'w_wood w_wood_kind w_grade w_own_tool',
    'Слесарь, сантехник': 'w_plumb w_grade w_own_tool',
    'Оператор оборудования': 'w_operator w_grade',
    'Кузнец, литейщик': 'w_forge w_own_tool w_portfolio',
    'Сыродел, мастер переработки': 'w_dairy w_medbook',
    'Повар, кондитер': 'w_cuisine w_kitchen_place w_grade w_medbook',
    'Швея, закройщик': 'w_sewing w_sew_machine w_grade',
    'Ветеринар': 'w_animals w_accred w_own_car',
    'Пчеловодство, животноводство': 'w_animals w_medbook',
    'Агроном, зоотехник': 'w_crops w_own_car',
    'Программирование, Разработка': 'w_dev_role w_stack w_level w_portfolio',
    'Тестирование': 'w_test w_stack w_level',
    'Аналитика, Data Science': 'w_data w_level',
    'Дизайн, графика': 'w_design w_soft w_level w_portfolio',
    'Дизайнер, художник': 'w_design w_soft w_portfolio',
    'Архитектор': 'w_build_object w_soft w_norm w_portfolio',
    'Бухгалтерия': 'w_acc_area w_tax w_acc_soft',
    'Кредитный специалист': 'w_credit w_crm',
    'Юрисконсульт': 'w_law w_advocate',
    'Врач': 'w_med_spec w_accred',
    'Медсестра, фельдшер': 'w_med_spec w_accred w_medbook',
    'Преподаватель, репетитор': 'w_subject w_pupils',
    'Переводчик': 'w_languages w_translate',
    'Тренер': 'w_sport w_pupils',
    'Фото, видео, звукооператоры': 'w_shoot w_own_gear w_portfolio',
    'Журналистика, СМИ': 'w_text w_portfolio',
    'Народные промыслы, ремёсла': 'w_craft w_own_tool w_portfolio',
    'Флорист, декоратор': 'w_floral w_portfolio',
    'Кладовщик, Приемщик товаров': 'w_store w_store_soft w_forklift',
    'Продавец': 'w_trade w_cash w_medbook',
    'Кассир': 'w_cash w_medbook',
    'Менеджер по продажам': 'w_trade w_crm',
    'Менеджер по закупкам': 'w_supply w_crm',
    'Логистика, ВЭД': 'w_logist w_languages',
    'Диспетчер': 'w_logist w_crm',
    'SMM': 'w_market w_portfolio',
    'Маркетинг': 'w_market w_portfolio',
    'Бизнес-консультант': 'w_consult',
    'Руководитель проектов': 'w_lead w_crm',
    'Административный директор': 'w_lead w_office',
    'Офис-менеджер, ассистент': 'w_office w_crm',
    'HR-менеджер': 'w_lead w_crm',
    'Прораб, мастер СМР': 'w_build_object w_lead w_norm',
    'Инженер строительного контроля': 'w_build_object w_norm',
    'Инженер-технолог': 'w_tech_area w_soft',
    'Горный инженер': 'w_tech_area w_grade',
    'Автослесарь, автомеханик': 'w_auto w_grade w_own_tool',
    'Автосервис, автомойка': 'w_auto',
    'Разнорабочий': 'w_labour w_height',
    'Охранник, контролёр': 'w_security w_licence',
    'Массажист, косметолог': 'w_beauty w_medbook',
    'Домработница, няня': 'w_home w_medbook',
    'Администратор гостиницы': 'w_hotel w_languages',
    'Агент по недвижимости': 'w_estate w_crm',
}

# Варианты, допустимые у специализации: «Лёгкий коммерческий» у тракториста
# не спрашивают.
ALLOWED = {
    ('Тракторист', 'w_licence'): ['B', 'C', 'Тракторные (Гостехнадзор)'],
    ('Водитель', 'w_vehicle'): ['Легковой', 'Лёгкий коммерческий', 'Грузовой до 10 т',
                                'Фура', 'Автобус'],
    ('Водитель', 'w_licence'): ['B', 'BE', 'C', 'CE', 'D', 'M'],
    ('Охранник, контролёр', 'w_licence'): ['B'],
    ('Ветеринар', 'w_animals'): ['Коровы', 'Козы и овцы', 'Свиньи', 'Птица', 'Лошади',
                                 'Домашние питомцы'],
    ('Архитектор', 'w_soft'): ['AutoCAD', 'Revit', 'ArchiCAD', 'Blender'],
    ('Инженер-технолог', 'w_soft'): ['AutoCAD'],
    ('Дизайн, графика', 'w_soft'): ['Figma', 'Photoshop', 'Illustrator', 'Blender'],
    ('Дизайн, графика', 'w_design'): ['Интерфейсы', 'Фирменный стиль', 'Полиграфия',
                                      'Иллюстрация'],
    ('Дизайнер, художник', 'w_design'): ['Интерьеры', 'Ландшафт', 'Иллюстрация'],
    ('Врач', 'w_med_spec'): ['Общая практика', 'Педиатрия', 'Терапия', 'Реабилитация'],
    ('Горный инженер', 'w_tech_area'): ['Горное дело'],
    ('Инженер-технолог', 'w_tech_area'): ['Пищевое', 'Металлообработка',
                                          'Деревообработка', 'Швейное', 'Химическое'],
}

# Слово в названии → обязательное значение (код, подпись).
HINTS = [
    (r'категории c', 'w_licence', 'C'),
    (r'солнечн|фотомодул', 'w_el_works', 'Солнечные панели'),
    (r'проводк', 'w_el_works', 'Проводка'),
    (r'сруб', 'w_wood', 'Срубы'), (r'мебел|краснодерев', 'w_wood', 'Мебель'),
    (r'кровельщик', 'w_finish', 'Кровля'), (r'печник', 'w_finish', 'Печи и камины'),
    (r'стены и полы', 'w_finish', 'Полы'), (r'каменщик', 'w_build', 'Кирпичная кладка'),
    (r'пилорам', 'w_operator', 'Пилорама'), (r'сушильн', 'w_operator', 'Сушильный комплекс'),
    (r'дробилк', 'w_operator', 'Дробилка и пресс'), (r'доильн', 'w_operator', 'Доильный зал'),
    (r'сортировк', 'w_operator', 'Сортировочная линия'),
    (r'печатн', 'w_operator', 'Печатная установка'),
    (r'крановщик', 'w_operator', 'Портальный кран'), (r'прачечн', 'w_operator', 'Прачечная'),
    (r'пекарь', 'w_cuisine', 'Выпечка и хлеб'), (r'пекарь', 'w_kitchen_place', 'Пекарня'),
    (r'кондитер', 'w_cuisine', 'Десерты'), (r'спецодежд', 'w_sewing', 'Спецодежда'),
    (r'пасек|пасечник|пчеловод', 'w_animals', 'Пчёлы'), (r'доярк', 'w_animals', 'Коровы'),
    (r'скотник', 'w_animals', 'Коровы'), (r'фронтенд', 'w_dev_role', 'Фронтенд'),
    (r'интеграци', 'w_dev_role', 'Интеграции'), (r'интерфейс|ux', 'w_design', 'Интерфейсы'),
    (r'первичк', 'w_acc_area', 'Первичка'), (r'якутск', 'w_languages', 'Якутский'),
    (r'воркаут', 'w_sport', 'Воркаут'), (r'видеосъ', 'w_shoot', 'Видео'),
    (r'семейн', 'w_shoot', 'Портреты и семья'), (r'технический писатель', 'w_text',
                                                 'Техническая документация'),
    (r'редактор', 'w_text', 'Редактура'), (r'гончар', 'w_craft', 'Гончарное дело'),
    (r'по дереву', 'w_craft', 'Резьба по дереву'), (r'по камню', 'w_craft', 'Камень'),
    (r'гравиров', 'w_craft', 'Гравировка'), (r'инвентаризац', 'w_store', 'Инвентаризация'),
    (r'приёмщик', 'w_store', 'Приёмка'), (r'выдачи', 'w_store', 'Выдача заказов'),
    (r'грант', 'w_consult', 'Гранты'), (r'кооператив', 'w_consult', 'Кооперация'),
    (r'финансов', 'w_consult', 'Финансы'), (r'пищев', 'w_tech_area', 'Пищевое'),
    (r'выездной бригады', 'w_med_spec', 'Выездная бригада'),
    (r'общей практики', 'w_med_spec', 'Общая практика'),
    (r'аудитор', 'w_test', 'Аудит кода'), (r'подбора|протокола', 'w_test', 'Безопасность'),
    (r'подготовку площадки|стройк', 'w_labour', 'Подсобные на стройке'),
    (r'сортировк', 'w_labour', 'Сортировка и упаковка'),
    (r'секретарь', 'w_office', 'Протоколы собраний'),
    (r'с допуском', 'w_el_group', 'IV'),
]

# У этих слов ответ один: «Пекарь» не в «Горячем цехе», «Пасечник» не с коровами.
EXCLUSIVE = {'w_labour', 'w_operator', 'w_animals', 'w_craft', 'w_wood'}

REMOTE = {
    'Программирование, Разработка', 'Тестирование', 'Аналитика, Data Science',
    'Дизайн, графика', 'Бухгалтерия', 'Юрисконсульт', 'Переводчик',
    'Журналистика, СМИ', 'SMM', 'Маркетинг', 'Бизнес-консультант',
}
TRAVEL = {'Водитель', 'Логистика, ВЭД', 'Агент по недвижимости', 'Ветеринар'}
HIGHER = REMOTE | {
    'Врач', 'Архитектор', 'Преподаватель, репетитор', 'Горный инженер',
    'Инженер-технолог', 'Инженер строительного контроля', 'Ветеринар',
    'Агроном, зоотехник', 'HR-менеджер', 'Руководитель проектов',
    'Административный директор', 'Кредитный специалист', 'Логистика, ВЭД',
}
# Оплата в месяц, рублей: нижняя и верхняя граница «от».
PAY = {'Разнорабочий': (45, 70), 'Кассир': (40, 55), 'Охранник, контролёр': (40, 55),
       'Программирование, Разработка': (110, 220), 'Сварщик': (80, 130),
       'Врач': (90, 150), 'Тестирование': (80, 150)}


def _attributes(env):
    Attribute = env['coop.attribute'].sudo()
    Option = env['coop.attribute.option'].sudo()
    out = {}
    for index, (code, name, kind, unit, widget, options) in enumerate(ATTRS):
        values = {'name': name, 'value_type': kind, 'unit': unit,
                  'filter_widget': widget, 'sequence': 5000 + index * 10,
                  'active': True}
        if code == 'w_grade':
            values.update(value_min=1, value_max=8)
        attribute = Attribute.with_context(active_test=False).search(
            [('code', '=', code)], limit=1)
        if attribute:
            attribute.write(values)
        else:
            attribute = Attribute.create(dict(values, code=code))
        _ensure_options(Option, attribute, options)
        out[code] = attribute
    return out


def _assign(env, attributes):
    Spec = env['coop.specialization'].sudo()
    Category = env['coop.specialization.category'].sudo()
    Assignment = env['coop.attribute.assignment'].sudo()
    for name, category_name in NEW_SPECS:
        category = Category.search([('name', '=', category_name)], limit=1)
        if category and not Spec.search_count([('name', '=', name)]):
            Spec.create({'name': name, 'category_id': category.id})
    linked = 0
    for name, codes in SETS.items():
        spec = Spec.search([('name', '=', name)], limit=1)
        if not spec:
            _logger.info('483: специализация «%s» не найдена', name)
            continue
        for order, code in enumerate(codes.split()):
            attribute = attributes[code]
            found = Assignment.search([
                ('attribute_id', '=', attribute.id),
                ('specialization_id', '=', spec.id)], limit=1)
            values = {'sequence': (order + 1) * 10}
            labels = ALLOWED.get((name, code))
            if labels:
                slugs = [_slug(x) for x in labels]
                values['option_ids'] = [(6, 0, attribute.option_ids.filtered(
                    lambda o: o.code in slugs).ids)]
            if found:
                found.write(values)
            else:
                Assignment.create(dict(
                    values, attribute_id=attribute.id, specialization_id=spec.id))
                linked += 1
    env.flush_all()
    return linked


def _respecialize(env):
    """Специализация вакансии — по её названию, а не жребием."""
    by_name = {s.name: s.id for s in env['coop.specialization'].sudo().search([])}
    moved = 0
    for vacancy in env['coop.vacancy'].sudo().with_context(
            active_test=False).search([]):
        title = (vacancy.name or '').lower()
        spec = next((by_name.get(n) for rx, n in BY_TITLE
                     if re.search(rx, title)), None)
        if spec and vacancy.coop_specialization_id.id != spec:
            vacancy.coop_specialization_id = spec
            moved += 1
    return moved


def _values(record, rnd):
    """Правдоподобные значения набора записи; пустое уже заполненное не трогаем."""
    title = (record.name or '').lower()
    out = {}
    for item in record.coop_specialization_id.attribute_definition or []:
        code, kind = item['name'], item['type']
        pairs = [(x[0], x[1]) for x in item.get('selection') or item.get('tags') or []]
        codes = [p[0] for p in pairs]
        hints = [_slug(label) for rx, c, label in HINTS
                 if c == code and re.search(rx, title) and _slug(label) in codes]
        if not hints and rnd.random() < 0.18:
            continue        # не все заполняют анкету до конца
        if kind == 'boolean':
            value = rnd.random() < 0.55
            if not value:
                continue
        elif kind == 'integer':
            value = rnd.randint(3, 6) if code == 'w_grade' else rnd.choice(
                [3, 5, 6, 8, 10, 12, 15, 20])
        elif not codes:
            continue
        elif kind == 'selection':
            value = hints[0] if hints else rnd.choice(codes)
        elif hints and code in EXCLUSIVE:
            value = hints
        else:
            value = list(dict.fromkeys(hints + rnd.sample(
                codes, min(len(codes), rnd.choice([1, 2, 2, 3])))))
            value = [c for c in codes if c in value]      # порядок справочника
        out[code] = value
    # Категории, названные в умениях, — и есть права: транспорт под них.
    text = ' '.join([title] + [n.lower() for n in record.skill_ids.mapped('name')])
    # В умениях буквы бывают и кириллицей.
    named = [c for c, rx in (('B', 'b|в'), ('C', 'c|с'), ('CE', 'ce|се'), ('D', 'd|д'))
             if re.search(r'категори[яи] (%s)' % rx, text)]
    if named and record.coop_specialization_id.name == 'Водитель':
        out['w_licence'] = [_slug(c) for c in named]
        fit = {'B': ['Легковой', 'Лёгкий коммерческий'],
               'C': ['Грузовой до 10 т'], 'CE': ['Фура'], 'D': ['Автобус']}
        out['w_vehicle'] = [_slug(rnd.choice(fit[c])) for c in named]
        if 'CE' not in named and out.get('w_route') == _slug('Международные'):
            out['w_route'] = _slug('По области')
    # Права — под транспорт: фура без CE и автобус без D не бывают.
    if out.get('w_route') == _slug('Международные'):
        out['w_vehicle'] = [_slug('Фура')]
    need = {'Легковой': 'B', 'Лёгкий коммерческий': 'B', 'Фура': 'CE',
            'Грузовой до 10 т': 'C', 'Автобус': 'D'}
    vehicles = {_slug(v): _slug(c) for v, c in need.items()}
    for vehicle in out.get('w_vehicle') or []:
        if vehicle in vehicles:
            out['w_licence'] = list(dict.fromkeys(
                (out.get('w_licence') or []) + [vehicles[vehicle]]))
    if record.coop_specialization_id.name == 'Водитель':
        # Легковая категория есть у любого водителя; опасный груз — грузовик.
        licences = (out.get('w_licence') or []) + ['b']
        out['w_licence'] = [c for c in ('b', 'be', 'c', 'ce', 'd', 'm')
                            if c in licences]
        if not {'c', 'ce'} & set(out['w_licence']):
            out.pop('w_adr', None)
    if out.get('w_acc_area') and _slug('Весь учёт') in out['w_acc_area']:
        out['w_acc_area'] = [_slug('Весь учёт')]
    if not out.get('w_vehicle') or _slug('Фура') not in out['w_vehicle']:
        out.pop('w_tacho', None)
    return out


def _fill_attrs(env, model):
    filled = 0
    for record in env[model].sudo().with_context(
            active_test=False, tracking_disable=True).search(
                [('coop_specialization_id', '!=', False)]):
        if any(v not in (None, False, [], '')
               for v in (record.attrs._values or {}).values()) \
                if record.attrs else False:
            continue
        values = _values(record, random.Random(483000 + record.id))
        if values:
            record.attrs = values
            filled += 1
    return filled


def _fill_vacancy_terms(env):
    Term = env['coop.vacancy.term'].sudo()
    term = {t.name: t.id for t in Term.search([])}
    done = paid = 0
    for vacancy in env['coop.vacancy'].sudo().with_context(
            active_test=False, tracking_disable=True).search([]):
        rnd = random.Random(483900 + vacancy.id)
        title = (vacancy.name or '').lower()
        # График часто назван в тексте: «вахтовый график», «смены 2/2».
        text = title + ' ' + (vacancy.description or '').lower()
        spec = vacancy.coop_specialization_id.name
        remote, once = spec in REMOTE, vacancy.employment in ('project', 'volunteer')
        values = {}
        if 'неполный день' in title or 'подработка' in title or 'полставки' in title:
            if vacancy.employment == 'full':
                values['employment'] = 'part'
        part = values.get('employment', vacancy.employment) == 'part'
        if not vacancy.work_schedule:
            values['work_schedule'] = (
                'rotation' if 'вахт' in text else
                'shift' if re.search(r'смен(ами|ы|а|у)', text) else
                'fixed' if 'на полный день' in title and 'вахт' not in text else
                'flexible' if remote or once or part else
                rnd.choice(['fixed', 'fixed', 'shift', 'shift', 'flexible']))
        schedule = values.get('work_schedule', vacancy.work_schedule)
        if not vacancy.work_format:
            values['work_format'] = (
                'onsite' if schedule == 'rotation' else
                rnd.choice(['remote', 'remote', 'hybrid']) if remote else
                'travel' if spec in TRAVEL else 'onsite')
        if not vacancy.work_hours:
            values['work_hours'] = (
                rnd.choice(['4', '6']) if part else
                'free' if once or schedule == 'flexible' else
                '12' if schedule == 'rotation' else
                rnd.choice(['8', '12', '12']) if schedule == 'shift' else '8')
        if not vacancy.pay_frequency and vacancy.reward_kind == 'money':
            values['pay_frequency'] = (
                'result' if once else 'twice' if vacancy.contract_kind == 'labour'
                else rnd.choice(['day', 'week', 'twice', 'month', 'result']))
        if not vacancy.benefit_ids:
            pool = ['Инструмент и материалы', 'Обучение'] if not remote else ['Обучение']
            if not remote:
                pool += ['Питание', 'Спецодежда', 'Проезд']
            names = rnd.sample(pool, rnd.randint(0, min(3, len(pool))))
            if schedule == 'rotation':
                names += ['Проживание', 'Проезд', 'Питание']
            if vacancy.contract_kind == 'labour' and rnd.random() < 0.25:
                names.append('Медицинская страховка')
            if vacancy.partner_id.coop_cooperative_kind and rnd.random() < 0.4:
                names.append('Членство в кооперативе')
            values['benefit_ids'] = [(6, 0, sorted({
                term[n] for n in names if n in term}))]
        if not vacancy.audience_ids and rnd.random() < 0.55:
            # Подросткам — только лёгкая работа без опыта и не вахта.
            pool = ['Старше 45 лет', 'Пенсионеры', 'Студенты']
            if remote or part:
                pool.append('Люди с нарушениями здоровья')
            light = (vacancy.employment == 'volunteer' or re.search(
                r'волонтёр|библиотекар|помощник', title))
            if light and schedule != 'rotation':
                pool.append('От 16 лет')
            values['audience_ids'] = [(6, 0, [term[n] for n in rnd.sample(
                pool, rnd.randint(1, 2)) if n in term])]
        if (vacancy.state == 'published' and vacancy.reward_kind == 'money'
                and not vacancy.pay_from and not vacancy.pay_to
                and not once and vacancy.pay_period == 'month'
                and rnd.random() < 0.85):
            low, high = PAY.get(spec, (50, 95))
            amount = rnd.randint(low, high) * 1000
            if part:
                amount = round(amount * 0.5 / 1000) * 1000
            values['pay_from'] = amount
            if rnd.random() < 0.5:
                values['pay_to'] = round(amount * 1.3 / 5000) * 5000
                if values['pay_to'] <= amount:
                    values.pop('pay_to')
            paid += 1
        if values:
            vacancy.write(values)
            done += 1
    return done, paid


def _fill_education(env):
    done = 0
    for offer in env['coop.skill.offer'].sudo().with_context(
            active_test=False, tracking_disable=True).search(
                [('education', '=', False)]):
        # У организации образования не бывает, у человека — по профессии.
        if offer.partner_id.is_company:
            continue
        rnd = random.Random(483500 + offer.id)
        offer.education = rnd.choice(
            ['higher', 'higher', 'higher', 'unfinished']
            if offer.coop_specialization_id.name in HIGHER
            else ['vocational', 'vocational', 'school', 'higher'])
        done += 1
    return done


def load_483_work(env):
    attributes = _attributes(env)
    linked = _assign(env, attributes)
    moved = _respecialize(env)
    terms, paid = _fill_vacancy_terms(env)
    vacancies = _fill_attrs(env, 'coop.vacancy')
    offers = _fill_attrs(env, 'coop.skill.offer')
    education = _fill_education(env)
    _logger.info(
        '483 работа: привязок %s, специализаций исправлено %s, условия у %s, '
        'оплата у %s, поля профессии у %s вакансий и %s навыков, образование у %s',
        linked, moved, terms, paid, vacancies, offers, education)
