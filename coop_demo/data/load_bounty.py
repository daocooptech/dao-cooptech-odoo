# -*- coding: utf-8 -*-
"""Задачи рабочей группы, менеджер сообщества и токены на балансах.

Задачи взяты не с потолка: это то, что действительно нужно проекту на
нынешнем этапе — перенос разделов, правовой разбор, переводы, тексты.
Демонстрационный раздел «Помощь проекту» на выдуманных задачах выглядел бы
пустым обещанием, а на настоящих по нему сразу видно, чем помочь.

Токены раздаются части участников, чтобы работало продвижение: объявление
без баланса продвинуть нельзя, и раздел «Ресурсы» показывал бы кнопку,
которая всегда отказывает.
"""
import logging
import re
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

# Состояния задач разведены намеренно: на экране должны быть видны все
# стадии, а не только «опубликовано». По одному состоянию не понять, как
# устроен путь от заявки до приёмки.
TASKS = [
    ('Перенести раздел «Навыки» из макета на движок',
     'Каталог навыков: модель, карточка, поиск и наполнение из '
     '<code>skills.html</code> прототипа. Готово, когда раздел открывается '
     'в меню и содержит те же навыки, что в макете.',
     'Программирование, Разработка', 120, 'published'),
    ('Разобрать правовой статус токенов платформы по 282-ФЗ',
     'Закон вступает в силу 01.09.2026. Нужно заключение: не меняет ли он '
     'квалификацию внутренней единицы платформы, которой оплачивается '
     'продвижение. Готово, когда есть письменный разбор со ссылками на нормы.',
     'Юрисконсульт', 200, 'published'),
    ('Вычитать тексты интерфейса каталога организаций',
     'Проверить формулировки на экранах: подсказки полей, пустые состояния, '
     'сообщения об ошибках. Готово, когда правки внесены и вычитаны повторно.',
     'Переводчик', 60, 'published'),
    ('Собрать список кооперативов Дербента и окрестностей',
     'Открытые источники: реестры, сайты, местная пресса. Нужны название, '
     'форма, город, чем занимаются. Готово, когда список сверен и оформлен '
     'таблицей.', 'Аналитика, Data Science', 80, 'published'),
    ('Нарисовать иллюстрации для раздела «Проекты»',
     'Четыре иллюстрации в стиле платформы: сбор вскладчину, распределение '
     'долей, общее собрание, приёмка работ. Готово, когда файлы приняты в '
     'исходниках.', 'Дизайн, графика', 150, 'published'),
    ('Проверить каталог ресурсов на мобильном',
     'Пройти каталог и карточку ресурса на телефоне, записать всё, что '
     'ломается или нечитаемо. Готово, когда список замечаний передан со '
     'снимками экрана.', 'Веб-дизайн', 50, 'assigned'),
    ('Описать порядок приёма в кооператив для справки платформы',
     'Пошагово: заявление, решение общего собрания, паевой взнос, запись в '
     'реестре. Со ссылками на закон 3085-1. Готово, когда текст согласован '
     'с юристом.', 'Юрисконсульт', 90, 'submitted'),
    ('Перевести описание платформы на английский',
     'Лендинг и раздел «На чём мы стоим». Не подстрочник: текст должен '
     'читаться носителем. Готово, когда перевод вычитан.',
     'Переводчик', 110, 'accepted'),
]

# Восьми задач на раздел мало: на них не видно ни поиска, ни отбора по
# роду занятий, ни постраничной навигации — а именно этим раздел и
# живёт. Правило наполнения каталога одно на платформу: сто-двести
# примеров, разных по состоянию и вознаграждению.
#
# Задачи ниже — рабочие дела кооператива и платформы: то, что
# действительно поручают участнику за вознаграждение. Сверху остаются
# восемь настоящих задач самой платформы — они первые в списке.
MORE = [
    ('Собрать список поставщиков кормов по области', 'Аналитика, Data Science'),
    ('Свести в таблицу цены на пиломатериал у трёх поставщиков',
     'Менеджер по закупкам'),
    ('Подготовить смету на ремонт кровли склада', 'Прораб, мастер СМР'),
    ('Проверить сметы подрядчиков на монтаж теплицы',
     'Инженер строительного контроля'),
    ('Оформить документы на приём трёх новых пайщиков', 'Юрисконсульт'),
    ('Составить договор поставки для кооперативной лавки', 'Юрисконсульт'),
    ('Свести отчёт ревизионной комиссии за полугодие', 'Бухгалтерия'),
    ('Разнести первичку по складу за месяц', 'Бухгалтерия'),
    ('Снять видео о работе пасеки для каталога',
     'Фото, видео, звукооператоры'),
    ('Сделать фотографии продукции для карточек товаров',
     'Фото, видео, звукооператоры'),
    ('Написать тексты для страницы кооператива', 'Журналистика, СМИ'),
    ('Вычитать описания в каталоге ресурсов', 'Переводчик'),
    ('Перевести правила сообщества на татарский', 'Переводчик'),
    ('Настроить учёт смен в программе «Артель»',
     'Программирование, Разработка'),
    ('Написать выгрузку остатков склада в таблицу',
     'Программирование, Разработка'),
    ('Проверить каталог вакансий на телефоне', 'Тестирование'),
    ('Прогнать проверку форм заявок перед запуском', 'Тестирование'),
    ('Нарисовать значки для раздела складчины', 'Дизайн, графика'),
    ('Сверстать листовку о кооперативе к ярмарке', 'Дизайн, графика'),
    ('Провести занятие по кооперативному учёту',
     'Преподаватель, репетитор'),
    ('Подготовить памятку новичку кооператива', 'Преподаватель, репетитор'),
    ('Помочь с подключением щитка в мастерской',
     'Электромонтажник, электромонтер, техник-электрик'),
    ('Заменить проводку в складском помещении',
     'Электромонтажник, электромонтер, техник-электрик'),
    ('Сварить ворота для площадки', 'Сварщик'),
    ('Заварить раму прицепа', 'Сварщик'),
    ('Собрать стеллажи для склада', 'Столяр, плотник'),
    ('Сделать столы для общей мастерской', 'Столяр, плотник'),
    ('Выложить кирпичом подсобное помещение',
     'Бетонщик, арматурщик, каменщик'),
    ('Залить площадку под навес', 'Бетонщик, арматурщик, каменщик'),
    ('Перевезти оборудование между площадками', 'Водитель'),
    ('Развезти заказы складчины по точкам выдачи', 'Водитель'),
    ('Вспахать участок под посадку', 'Тракторист'),
    ('Скосить траву на общей территории', 'Тракторист'),
    ('Осмотреть пасеку перед откачкой', 'Пчеловодство, животноводство'),
    ('Проверить стадо перед выгоном', 'Ветеринар'),
    ('Составить план севооборота на сезон', 'Агроном, зоотехник'),
    ('Подобрать сорта для закрытого грунта', 'Агроном, зоотехник'),
    ('Сшить комплект спецодежды для бригады', 'Швея, закройщик'),
    ('Отремонтировать тент на прицепе', 'Швея, закройщик'),
    ('Починить мотоблок перед сезоном', 'Автослесарь, автомеханик'),
    ('Перебрать двигатель мотопомпы', 'Автослесарь, автомеханик'),
    ('Навести порядок в складском учёте', 'Кладовщик, Приемщик товаров'),
    ('Принять и разложить партию удобрений', 'Кладовщик, Приемщик товаров'),
    ('Помочь на разгрузке и уборке площадки', 'Разнорабочий'),
    ('Подготовить площадку к монтажу', 'Разнорабочий'),
    ('Провести день открытых дверей кооператива', 'Маркетинг'),
    ('Вести страницу кооператива неделю', 'SMM'),
    ('Обзвонить участников по заявкам на складчину', 'Диспетчер'),
    ('Дежурить на выдаче заказов в субботу', 'Продавец'),
    ('Стоять на прилавке на ярмарке выходного дня', 'Продавец'),
    ('Сверить остатки по кассе за неделю', 'Кассир'),
    ('Принять заявки на обучение и записать группу',
     'Офис-менеджер, ассистент'),
    ('Помочь с уборкой после ярмарки', 'Разнорабочий'),
    ('Собрать обратную связь у пайщиков после собрания',
     'Бизнес-консультант'),
    ('Подготовить справку о правовых формах для новичков', 'Юрисконсульт'),
]

DESCRIPTIONS = [
    'Задача разовая, оплачивается по приёмке. Готово, когда результат '
    'сдан и принят менеджером сообщества.',
    'Сроки обсуждаются, но не больше двух недель. Готово, когда сделано '
    'и подтверждено тем, кто задачу поставил.',
    'Материалы и доступ даёт кооператив. Готово, когда результат принят '
    'без замечаний.',
    'Можно взяться вдвоём и разделить оплату. Готово, когда '
    'результат выложен в ленту задачи.',
]

# Только те состояния, которые загрузчик проводит действиями:
# «в работе» и «сдано» он получает из заявки и приёмки, а не
# проставлением поля.
STATES = (['published'] * 7) + ['draft', 'submitted', 'accepted']
REWARDS = [40, 60, 80, 100, 120, 150, 180, 200, 250, 300]


def more_tasks(how_many=112):
    """Список кортежей той же формы, что и `TASKS`."""
    gathered = []
    for number in range(how_many):
        title, specialization = MORE[number % len(MORE)]
        if number >= len(MORE):
            title = '%s (%s)' % (title, CITIES[number % len(CITIES)])
        gathered.append((
            title,
            DESCRIPTIONS[number % len(DESCRIPTIONS)],
            specialization,
            REWARDS[number % len(REWARDS)],
            STATES[number % len(STATES)],
        ))
    return gathered


CITIES = [
    'Дербент', 'Тюмень', 'Пермь', 'Казань', 'Волгоград', 'Хабаровск',
    'Ростов-на-Дону', 'Новосибирск', 'Красноярск', 'Воронеж', 'Уфа',
    'Екатеринбург', 'Самара', 'Челябинск', 'Ярославль', 'Владивосток',
]

TASKS = TASKS + more_tasks()



# Наборы способов у задач платформы (решение 671 п. 7): оба способа,
# только токены, только зачётом в рублях.
PLATFORM_METHOD_SETS = [lambda m: [m['tokens'].id]] * 3

# Решения администратора по спорам, закрытым в пользу исполнителя
# (решение 194: решение записывается с объяснением).
DISPUTE_DECISIONS = [
    'Результат сдан в срок и совпадает с описанием задачи, замечаний автор '
    'не направил. Засчитано в пользу исполнителя.',
    'Исполнитель приложил результат целиком, автор за семь дней не ответил '
    'и на запрос администратора. Засчитано в пользу исполнителя.',
]

# Задачи платформы в состояниях, которых нет у первых ста двадцати:
# отменённые, спорные, разобранные спором.
EXTRA_PLATFORM = [
    ('Записать видеоинструкцию «Как взять задачу»', 'Журналистика, СМИ', 140, 'dispute'),
    ('Сверить переводы интерфейса на казахский', 'Переводчик', 180, 'dispute'),
    ('Проверить окно заявки на задачу с телефона', 'Тестирование', 60, 'dispute'),
    ('Свести ответы опроса пайщиков в таблицу', 'Аналитика, Data Science', 90, 'dispute_resolved'),
    ('Подготовить памятку «Как оформить долю за задачу»', 'Юрисконсульт', 220, 'dispute_resolved'),
    ('Нарисовать значки способов оплаты', 'Дизайн, графика', 120, 'submitted'),
    ('Вычитать тексты страницы задач', 'Журналистика, СМИ', 70, 'submitted'),
    ('Перенести справочник ОКВЭД в каталог организаций', 'Программирование, Разработка', 260, 'assigned'),
    ('Описать порядок спора по задаче для справки', 'Юрисконсульт', 150, 'assigned'),
    ('Собрать список ярмарок Поволжья на зиму', 'Аналитика, Data Science', 80, 'cancelled'),
    ('Перевести лендинг на узбекский', 'Переводчик', 200, 'cancelled'),
    ('Снять ролик о складчине в Казани', 'Журналистика, СМИ', 160, 'cancelled_assigned'),
    ('Собрать каталог шаблонов договоров для кооперативов', 'Юрисконсульт', 190, 'overdue'),
    ('Записать подкаст о паевых взносах', 'Журналистика, СМИ', 110, 'overdue'),
    ('Перевести справку о спорах на английский', 'Переводчик', 130, 'dropped'),
    ('Проверить страницу проекта на планшете', 'Тестирование', 70, 'dropped'),
]

# Задачи проектов (решение 672): рубли, токены проекта, доля.
PROJECT_TEMPLATES = [
    ('Нарисовать логотип и фирменные цвета', 'Дизайн, графика',
     'Логотип в двух вариантах и три фирменных цвета. Готово, когда '
     'исходники переданы и логотип стоит на странице проекта.'),
    ('Написать тексты для страницы проекта', 'Журналистика, СМИ',
     'Описание, «зачем это нужно» и ответы на частые вопросы. Готово, '
     'когда тексты опубликованы на странице проекта.'),
    ('Собрать сайт-визитку проекта', 'Веб-дизайн',
     'Одна страница: что делаем, где купить, как связаться. Готово, когда '
     'сайт открывается по адресу проекта.'),
    ('Составить план продаж на первый год', 'Аналитика, Data Science',
     'Помесячно: объём, цена, каналы. Готово, когда таблица сверена с '
     'руководителем проекта.'),
    ('Подготовить договор с поставщиком сырья', 'Юрисконсульт',
     'Договор поставки с условиями о качестве и сроках. Готово, когда '
     'проект договора согласован сторонами.'),
    ('Настроить учёт расходов проекта', 'Бухгалтерия',
     'Статьи расходов и ежемесячный отчёт. Готово, когда первый месяц '
     'разнесён.'),
    ('Проверить страницу проекта на телефоне', 'Тестирование',
     'Пройти страницу и форму вклада, записать всё, что ломается. Готово, '
     'когда список замечаний передан со снимками экрана.'),
    ('Перевести описание проекта на английский', 'Переводчик',
     'Описание и условия участия. Готово, когда перевод вычитан.'),
    ('Собрать стеллажи в цеху', 'Столяр, плотник',
     'Четыре стеллажа по чертежу проекта, материал на месте. Готово, когда '
     'стеллажи стоят и выдерживают нагрузку.'),
    ('Сварить каркас навеса', 'Сварщик',
     'Каркас шесть на четыре метра по чертежу, металл на площадке. Готово, '
     'когда каркас принят руководителем проекта.'),
    ('Развезти пробную партию по точкам', 'Водитель',
     'Пять точек в пределах города, машина своя. Готово, когда все точки '
     'подтвердили приём.'),
    ('Подобрать сорта для теплицы', 'Агроном, зоотехник',
     'Пять сортов под наш климат с расчётом урожая. Готово, когда список '
     'согласован.'),
    ('Сшить фартуки с логотипом', 'Швея, закройщик',
     'Двадцать фартуков, ткань даёт проект. Готово, когда партия передана.'),
    ('Написать бота приёма заказов', 'Программирование, Разработка',
     'Заказ, оплата при получении, уведомление в общий чат. Готово, когда '
     'бот принял десять пробных заказов.'),
    ('Составить смету на ремонт помещения', 'Прораб, мастер СМР',
     'Смета по замерам с ценами двух поставщиков. Готово, когда смета '
     'согласована.'),
]

# Решение 690: задачи проекта — только его токенами.
PROJECT_METHOD_SETS = [('project_tokens',)]
PROJECT_STATES = ['published', 'published', 'published', 'draft', 'assigned',
                  'submitted', 'dispute', 'accepted', 'accepted', 'cancelled',
                  'published', 'dispute_resolved']
SHARES = [0.5, 1, 1.5, 2, 3, 5, 8]
SHARE_FORMS = ['token_share', 'certificate', 'contribution', False]


def _drive(task, state, index):
    """Довести задачу с утверждённым исполнителем до нужного состояния.

    Теми же действиями, что и в жизни: сдача ставит дату, спор открывает
    задание по расписанию, разобранный спор закрывает решение с
    объяснением.
    """
    today = fields.Date.context_today(task)
    if state in ('submitted', 'accepted', 'dispute', 'dispute_resolved'):
        if index % 4 == 0:
            # Каждая четвёртая — со второй версией: первую вернули с замечаниями.
            task._coop_do_submit(_link(task, 1), SUBMIT_NOTES[index % len(SUBMIT_NOTES)])
            task._coop_do_return(RETURN_NOTES[index % len(RETURN_NOTES)])
        task._coop_do_submit(_link(task, len(task.submission_ids) + 1),
                             SUBMIT_NOTES[(index + 1) % len(SUBMIT_NOTES)])
        days = 8 + index % 22 if state.startswith('dispute') else index % 6
        task.write({'submitted_on': today - timedelta(days=days)})
    if state == 'accepted':
        task.criterion_ids.write({'done': True})
        task.action_accept()
    elif state == 'dispute':
        task.criterion_ids[:1].write({'done': True})
    elif state == 'dispute_resolved':
        task.criterion_ids[:1].write({'done': True})
        task.write({'state': 'dispute', 'dispute_on': today - timedelta(days=index % 5),
                    'dispute_decision': DISPUTE_DECISIONS[index % len(DISPUTE_DECISIONS)]})
        task.message_post(body='Решение по спору — засчитать в пользу исполнителя: %s'
                          % task.dispute_decision)
        task.with_context(coop_bounty_force_accept=True).action_accept()
    elif state == 'cancelled_assigned':
        task.action_cancel()
    elif state == 'overdue':
        task.write({'deadline': today - timedelta(days=2 + index % 3)})
    elif state == 'dropped':
        task.write({'deadline': today - timedelta(days=9 + index % 5)})


def _apply(env, task, partner, index, message='Возьмусь, делал похожее.'):
    allowed = task.allowed_method_ids
    return env['coop.bounty.application'].sudo().create({
        'task_id': task.id,
        'partner_id': partner.id,
        'method_id': allowed[index % len(allowed)].id,
        'message': message,
    })


def _performers(env, people):
    """Исполнители — участники каталога и витринный человек.

    dashkevich среди них, чтобы под ним были видны задачи во всех
    состояниях со стороны исполнителя (демо видно под dashkevich).
    """
    showcase = env['res.users'].sudo().search([('login', '=', 'dashkevich')], limit=1)
    performers = list(people)
    if showcase:
        performers.insert(0, showcase.partner_id)
    return performers, showcase


def load_extra_platform_tasks(env, Task, manager, methods, specializations, people):
    performers, _showcase = _performers(env, people)
    if not performers:
        return 0
    today = fields.Date.context_today(Task)
    created = 0
    for index, (name, specialization, reward, state) in enumerate(EXTRA_PLATFORM):
        if Task.search_count([('name', '=', name)]):
            continue
        spec = specializations.get(specialization)
        task = Task.create({
            'name': name,
            'description': '<p>%s</p>' % DESCRIPTIONS[index % len(DESCRIPTIONS)],
            'criterion_ids': _criteria(DESCRIPTIONS[index % len(DESCRIPTIONS)], index),
            'reward_tokens': reward,
            'coop_specialization_id': spec.id if spec else False,
            'manager_id': manager.id,
            'allowed_method_ids': [(6, 0, PLATFORM_METHOD_SETS[index % 3](methods))],
            'deadline': today + timedelta(days=10 + index * 9),
        })
        created += 1
        task.action_publish()
        if state == 'cancelled':
            task.action_cancel()
            continue
        _apply(env, task, performers[index % len(performers)], index).action_approve()
        _drive(task, state, index)
    return created


def load_project_tasks(env, Task, methods, specializations):
    """Задачи проектов: платит организация проекта, не платформа."""
    Project = env['coop.project'].sudo()
    projects = Project.search([('partner_id.is_company', '=', True),
                               ('state', 'in', ('gathering', 'running'))],
                              order='id', limit=30)
    people = env['res.partner'].sudo().search(
        [('coop_is_participant', '=', True), ('is_company', '=', False)],
        order='id', limit=24)
    performers, showcase = _performers(env, people)
    if not projects or not performers:
        return 0

    # Потолок и форма доли — у каждой организации свои (решения 672, 673);
    # у трети потолка нет.
    orgs = projects.mapped('partner_id')
    for index, org in enumerate(orgs):
        if org.coop_labor_share_cap or org.coop_labor_share_form:
            continue
        org.write({'coop_labor_share_cap': (5, 10, 0)[index % 3],
                   'coop_labor_share_form': SHARE_FORMS[index % len(SHARE_FORMS)]})

    # Организации, где витринный человек вправе публиковать: часть задач
    # ставит он сам — так под ним видны и черновики, и заявки к ним.
    own_orgs = (showcase.coop_publisher_partner_ids.filtered('is_company')
                if showcase else env['res.partner'])

    Membership = env['coop.membership'].sudo()
    today = fields.Date.context_today(Task)
    used = set(Task.search([]).mapped('name'))
    # Шестьдесят задач проектов всего, а не за каждое обновление модуля:
    # загрузчик идёт при каждой выкатке.
    existing = Task.search_count([('payer_kind', '=', 'project')])
    created = 0
    index = -1
    attempts = 0
    count = len(projects)
    while existing + created < 60 and attempts < 400:
        attempts += 1
        index += 1
        project = projects[index % count]
        title, specialization, description = PROJECT_TEMPLATES[
            (index + index // count) % len(PROJECT_TEMPLATES)]
        payer = project.partner_id
        if own_orgs and index % 5 == 1:
            payer = own_orgs[(index // 5) % len(own_orgs)]
            project = _org_crowd_project(env, payer)
            name = '%s — %s' % (title, project.name if project else payer.name)
        else:
            name = '%s — «%s»' % (title, project.name)
        if name in used:
            continue
        used.add(name)

        codes = PROJECT_METHOD_SETS[index % len(PROJECT_METHOD_SETS)]
        state = PROJECT_STATES[index % len(PROJECT_STATES)]
        share = SHARES[index % len(SHARES)] if 'share' in codes else 0
        cap = payer.coop_labor_share_cap
        # Черновик может превышать потолок — так видно, почему его не
        # опубликовать; опубликованные — в пределах потолка.
        if cap and share > cap and state != 'draft':
            share = cap
        if showcase and payer in own_orgs:
            author = showcase
        else:
            author = Membership.search([
                ('organization_id', '=', payer.id), ('state', '=', 'active'),
                ('partner_id.user_ids', '!=', False)], limit=1).partner_id.user_ids[:1]
        spec = specializations.get(specialization)
        task = Task.create({
            'name': name,
            'description': '<p>%s</p>' % description,
            'criterion_ids': _criteria(description, index),
            'payer_id': payer.id,
            'project_id': project.id if project else False,
            'reward_tokens': (3 + (index * 7) % 38) * 1000 if set(codes) - {'share'} else 0,
            'share_percent': share,
            'allowed_method_ids': [(6, 0, [methods[c].id for c in codes])],
            'coop_specialization_id': spec.id if spec else False,
            'manager_id': author.id if author else False,
            'deadline': today + timedelta(days=5 + (index * 13) % 150),
        })
        created += 1
        if state == 'draft':
            continue
        task.action_publish()
        if state == 'published':
            # Отклики ждут автора: от нуля до трёх, разными способами.
            for shift in range(index % 4):
                partner = performers[(index + shift * 5) % len(performers)]
                if not task.application_ids.filtered(lambda a, p=partner: a.partner_id == p):
                    _apply(env, task, partner, index + shift,
                           'Могу начать на этой неделе, примеры пришлю в ленту задачи.')
            continue
        if state == 'cancelled':
            task.action_cancel()
            continue
        _apply(env, task, performers[index % len(performers)], index).action_approve()
        _drive(task, state, index)
    return created


# ── Ход задачи (№ 464): критерии, вопросы, сдачи, отзывы, подписки ──────

GENERIC_CRITERIA = [
    'Результат приложен к сдаче или выложен по ссылке',
    'Исходники переданы автору',
    'Замечания автора учтены',
    'Сделано к сроку, указанному в задаче',
    'Автор может пользоваться результатом без исполнителя',
]

QUESTIONS = [
    'Пришлите ссылку на похожий результат',
    'Сколько часов в неделю готовы уделять задаче?',
    'Чем будете пользоваться — программы, инструмент, материалы?',
    'Делали ли задачи для кооперативов или проектов платформы?',
]

ANSWERS = [
    'Похожее делал для сельхозкооператива весной, ссылку пришлю в ленту задачи.',
    'Часов десять в неделю, по вечерам и в субботу.',
    'Свои программы и инструмент, материалы — по договорённости.',
    'Да, две задачи на платформе, обе приняты без замечаний.',
    'Портфолио на странице профиля, последние задачи — сверху.',
    'Могу начать с понедельника, промежуточный результат — через неделю.',
]

SUBMIT_NOTES = [
    'Всё по критериям, исходники в архиве.',
    'Сделал основное, по второму пункту — два варианта на выбор.',
    'Готово, проверил на телефоне и компьютере.',
    'Результат по ссылке, коротко описал, где что лежит.',
    'Учёл замечания к прошлой версии, изменения отметил в описании.',
]

RETURN_NOTES = [
    'Не хватает исходников — приложите, пожалуйста.',
    'Второй пункт не выполнен: нужен вариант для тёмного фона.',
    'Поправьте сроки в таблице — сейчас они расходятся с планом.',
    'Результат хороший, но не учтены два замечания из ленты задачи.',
]

REVIEWS = {
    '5': ['Сделано раньше срока и аккуратно, работать приятно.',
          'Всё по критериям с первой версии, спасибо.',
          'Отвечали быстро, условия понятные, оплатили сразу.'],
    '4': ['Хороший результат, одна доработка по мелочи.',
          'Всё сделано, немного затянули со сроком.'],
    '3': ['Результат принят, но пришлось дважды напоминать.'],
    '2': ['Сдано с опозданием, доработки заняли больше задачи.'],
    '1': ['Результат пришлось переделывать почти целиком.'],
}
RATING_ROLL = ['5', '5', '5', '4', '5', '4', '3', '5', '4', '2', '5', '5', '4', '5', '3', '5', '5', '1', '4', '5']


def _criteria(description, index):
    """Критерии из «Готово, когда …» описания плюс один-два общих."""
    points = []
    text = description or ''
    if 'Готово, когда' in text:
        tail = text.split('Готово, когда', 1)[1].strip().rstrip('.')
        if tail:
            points.append(tail[0].upper() + tail[1:])
    for shift in range(1 + index % 2):
        points.append(GENERIC_CRITERIA[(index + shift * 2) % len(GENERIC_CRITERIA)])
    return [(0, 0, {'name': name, 'sequence': (number + 1) * 10})
            for number, name in enumerate(points)]


def _link(task, version):
    return 'https://cloud.daocoop.tech/s/t%sv%s' % (task.id, version)


def load_bounty_flow(env, Task):
    """Достроить ход у задач, заведённых до № 464: на сервере их 192.

    Только там, где пусто: загрузчик идёт при каждой выкатке и не должен
    ни дублировать записи, ни переписывать сделанное руками.
    """
    Submission = env['coop.bounty.submission'].sudo()
    Review = env['coop.bounty.review'].sudo()
    Answer = env['coop.bounty.answer'].sudo()
    tasks = Task.search([], order='id')
    for index, task in enumerate(tasks):
        description = re.sub(r'<[^>]+>', '', str(task.description or ''))
        if not task.criterion_ids:
            task.write({'criterion_ids': _criteria(description, index)})
        if task.state == 'accepted':
            task.criterion_ids.filtered(lambda c: not c.done).write({'done': True})
        if not task.question_ids and index % 3 == 0 and task.state in ('draft', 'published'):
            task.write({'question_ids': [
                (0, 0, {'name': QUESTIONS[(index + shift) % len(QUESTIONS)],
                        'sequence': (shift + 1) * 10, 'required': shift == 0})
                for shift in range(1 + index % 2)]})
        for number, application in enumerate(task.application_ids):
            if not application.proposed_deadline and task.deadline and (index + number) % 5:
                application.proposed_deadline = task.deadline - timedelta(days=(index + number) % 6)
            if task.question_ids and not application.answer_ids:
                for shift, question in enumerate(task.question_ids):
                    Answer.create({'application_id': application.id, 'question_id': question.id,
                                   'question': question.name,
                                   'answer': ANSWERS[(index + number + shift) % len(ANSWERS)]})
        if task.state in ('submitted', 'dispute', 'accepted') and task.assignee_id \
                and not task.submission_ids:
            day = task.submitted_on or task.accepted_on
            if index % 4 == 0:
                Submission.create({'task_id': task.id, 'partner_id': task.assignee_id.id,
                                   'version': 1, 'link': _link(task, 1),
                                   'note': SUBMIT_NOTES[index % len(SUBMIT_NOTES)],
                                   'state': 'returned', 'reviewed_on': day,
                                   'review_note': RETURN_NOTES[index % len(RETURN_NOTES)]})
            version = len(task.submission_ids) + 1
            Submission.create({'task_id': task.id, 'partner_id': task.assignee_id.id,
                               'version': version, 'link': _link(task, version),
                               'note': SUBMIT_NOTES[(index + 1) % len(SUBMIT_NOTES)],
                               'state': 'accepted' if task.state == 'accepted' else 'review',
                               'reviewed_on': task.accepted_on if task.state == 'accepted' else False})
        if task.state == 'accepted' and task.assignee_id and not task.review_ids:
            # Автор отзывается чаще исполнителя — как в сделках.
            for side, target, author, chance in (
                    ('author', task.assignee_id, task.payer_id, index % 7),
                    ('executor', task.payer_id, task.assignee_id, index % 3)):
                if not chance:
                    continue
                rating = RATING_ROLL[(index + len(side)) % len(RATING_ROLL)]
                bodies = REVIEWS[rating]
                Review.create({'task_id': task.id, 'side': side, 'rating': rating,
                               'author_id': author.id, 'target_id': target.id,
                               'body': bodies[index % len(bodies)]})

    # Подписки: часть участников и витринный человек.
    Subscription = env['coop.bounty.subscription'].sudo()
    specializations = env['coop.specialization'].sudo().search(
        [('id', 'in', tasks.mapped('coop_specialization_id').ids)], order='id')
    people = env['res.partner'].sudo().search(
        [('coop_is_participant', '=', True), ('is_company', '=', False)], order='id', limit=60)
    showcase = env['res.users'].sudo().search([('login', '=', 'dashkevich')], limit=1).partner_id
    if showcase and showcase not in people:
        people |= showcase
    for index, person in enumerate(people):
        if not specializations or Subscription.with_context(active_test=False).search_count(
                [('partner_id', '=', person.id)]):
            continue
        chosen = specializations[index % len(specializations)]
        if index % 2:
            chosen |= specializations[(index * 7 + 3) % len(specializations)]
        Subscription.create({
            'partner_id': person.id,
            'specialization_ids': [(6, 0, chosen.ids)] if index % 5 else [],
            'city': person.city if index % 3 else False,
            'active': bool(index % 9),
        })


# ── Краудсорсинг (решение 690): токены проектов, задачи — проектам ───────

TOKEN_ECONOMY = [
    '<p>1 токен — право получить продукцию проекта на 1 ₽ по прайсу проекта. '
    'Погашается продукцией до конца следующего сезона, в деньги не обменивается.</p>',
    '<p>Токен учитывает вклад в проект. Когда проект оформит юрлицо, вклад '
    'держателей оценивается и учитывается в уставном капитале — по закону '
    'страны проекта.</p>',
    '<p>1 токен — час услуг проекта по его прайсу. Действует год с начисления, '
    'передаётся другим участникам платформы.</p>',
]


def _demo_project_tokens(env):
    """Токены у демо-проектов — каждый описывает свой сам."""
    projects = env['coop.project'].sudo().search(
        [('partner_id.is_company', '=', True), ('state', 'in', ('gathering', 'running'))],
        order='id', limit=40)
    for index, project in enumerate(projects):
        if project.coop_token_name:
            continue
        letters = ''.join(word[0] for word in project.name.replace('«', ' ').replace('»', ' ').split()
                          if word[:1].isalpha())[:4].upper()
        project.write({
            'coop_token_name': 'Токен «%s»' % project.name,
            'coop_token_symbol': letters or 'ТП',
            'coop_token_economy': TOKEN_ECONOMY[index % len(TOKEN_ECONOMY)],
        })
    return projects


def _org_crowd_project(env, org):
    """Проект организации для её задач в краудсорсинге (решение 690).

    У организаций витринного человека (ПК «Родник», ОАО «Вектор
    Инжиниринг») проектов не было, и их задачи висели без проекта — а
    без проекта задачу в краудсорсинге не опубликовать. Проект заводится
    запущенным, с порогом 100 %: при пороге по умолчанию (70 %) запущенный
    проект требует плана на неполный сбор, и на этом падала загрузка.
    """
    Project = env['coop.project'].sudo()
    project = Project.search([('partner_id', '=', org.id)], order='id', limit=1)
    if project:
        return project
    cooperative = (org.coop_legal_form_id.code in ('pk', 'spk', 'artel')
                   or (org.name or '').startswith(('ПК ', 'СПК ')))
    short = (org.name or '').split('«')[-1].rstrip('»') or org.name
    try:
        with env.cr.savepoint():
            return Project.create({
                'name': 'Развитие %s' % org.name,
                'partner_id': org.id,
                'kind': 'cooperative' if cooperative else 'commercial',
                'state': 'running',
                'funding_rule': 'threshold',
                'funding_threshold': 100,
                'fallback_plan': 'Задачи выполняются по мере сбора: сначала те, '
                                 'на которые хватает собранного.',
                'city': org.city,
                'summary': 'Задачи %s в краудсорсинге: оплата токенами проекта.' % org.name,
                'coop_token_name': 'Токен «%s»' % short,
                'coop_token_symbol': ''.join(w[0] for w in short.split() if w[:1].isalpha())[:4].upper() or 'ТП',
                'coop_token_economy': TOKEN_ECONOMY[org.id % len(TOKEN_ECONOMY)],
            })
    except Exception:
        _logger.exception('Проект для задач «%s» не заведён', org.name)
        return Project


def _demo_tasks_to_projects(env, Task, methods):
    """Сгенерированные задачи «платформы» — задачами проектов (решение 690):
    у нашего проекта остаются только настоящие задачи."""
    # Задачи организаций без проекта — в проект организации.
    for task in Task.search([('payer_kind', '=', 'project'), ('project_id', '=', False)]):
        project = _org_crowd_project(env, task.payer_id)
        if project:
            task.with_context(coop_bounty_skip_fund_lock=True).write({'project_id': project.id})
    names = {name for name, *_rest in more_tasks()} | {row[0] for row in EXTRA_PLATFORM}
    projects = _demo_project_tokens(env)
    if not projects:
        return 0
    method = methods['project_tokens']
    moved = 0
    for index, task in enumerate(Task.search([('payer_kind', '=', 'platform'),
                                              ('name', 'in', list(names))], order='id')):
        project = projects[index % len(projects)]
        values = {'payer_id': project.partner_id.id, 'project_id': project.id, 'fund_id': False,
                  'allowed_method_ids': [(6, 0, method.ids)]}
        if task.payment_mode:
            values['payment_mode'] = 'project_tokens'
        task.with_context(coop_bounty_skip_fund_lock=True).write(values)
        task.application_ids.write({'method_id': method.id})
        moved += 1
    # Бывшие задачи «только за долю» — без суммы; доля больше не способ
    # оплаты (решение 690), сумма — в токенах проекта.
    for task in Task.search([('payer_kind', '=', 'project'), ('reward_tokens', '=', 0)]):
        task.write({'reward_tokens': (3 + (task.id * 7) % 38) * 100})

    # Принятые задачи проектов — начисление их токенов, если его нет.
    Move = env['coop.project.token.move'].sudo()
    for task in Task.search([('payer_kind', '=', 'project'), ('state', '=', 'accepted'),
                             ('project_id', '!=', False), ('assignee_id', '!=', False)]):
        if not Move.search_count([('task_id', '=', task.id)]):
            Move.create({'project_id': task.project_id.id, 'partner_id': task.assignee_id.id,
                         'amount': task.reward_tokens, 'task_id': task.id,
                         'date': task.accepted_on or fields.Date.context_today(task),
                         'description': 'Задача «%s»' % task.name})
    return moved


def grant_admin_roles(env):
    """Выдать администратору стенда все роли платформы.

    Решение владельца 137. Через XML это не работает: запись
    `base.user_admin` объявлена в базовом модуле с защитой от обновления,
    и наше переопределение загрузчик молча пропускает — ровно как было со
    знаком рубля и с reference-данными. На стенде это выглядело так:
    роли в файле есть, а администратор не может завести движение токенов.

    Само правило «платформа не сторона отношений участников» это не
    нарушает: сквозное правило доступа к членству живёт в этом же
    демонстрационном модуле, и на узле без него строгая модель остаётся.
    """
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    if not admin:
        return
    groups = [env.ref(xmlid, raise_if_not_found=False) for xmlid in (
        'coop_base.group_coop_platform',
        'coop_base.group_coop_member',
        'coop_base.group_coop_board',
        'coop_base.group_coop_audit',
        'coop_bounty.group_coop_community_manager',
    )]
    missing = [g for g in groups if g and g not in admin.group_ids]
    if missing:
        admin.sudo().write({'group_ids': [(4, g.id) for g in missing]})
        _logger.info('Администратору выданы роли: %s',
                     ', '.join(g.name for g in missing))


def load_bounty(env):
    # Через sudo: загрузчик вызывается при обновлении модуля, и права
    # текущего пользователя к демонстрационным данным отношения не
    # имеют — он их не создаёт, а получает вместе с модулем.
    Task = env['coop.bounty.task'].sudo()
    Partner = env['res.partner'].sudo()
    manager_group = env.ref('coop_bounty.group_coop_community_manager')

    # Менеджер сообщества — отдельная учётная запись рабочей группы. Роль
    # платформы, а не кооператива: прав в чужих кооперативах она не даёт.
    manager = env['res.users'].sudo().search([('login', '=', 'community')], limit=1)
    if not manager:
        manager = env['res.users'].sudo().create({
            'name': 'Тихонова Ольга Сергеевна',
            'login': 'community',
            'password': 'community',
            'group_ids': [(4, env.ref('base.group_user').id),
                          (4, manager_group.id),
                          (4, env.ref('coop_base.group_coop_platform').id)],
            'lang': 'ru_RU',
            'tz': 'Europe/Moscow',
        })
        manager.partner_id.write({'city': 'Москва', 'coop_is_participant': False})
    elif manager_group not in manager.group_ids:
        manager.write({'group_ids': [(4, manager_group.id)]})

    specializations = {s.name: s for s in env['coop.specialization'].sudo().search([])}
    # Исполнители берутся из каталога людей: задачу берёт участник, а не
    # абстрактный пользователь.
    people = Partner.search(
        [('coop_is_participant', '=', True), ('is_company', '=', False)],
        order='id', limit=8)

    methods = {m.code: m for m in env['coop.bounty.method'].sudo().with_context(
        active_test=False).search([])}
    created = 0
    for index, (name, description, specialization, reward, state) in enumerate(TASKS):
        task = Task.search([('name', '=', name)], limit=1)
        values = {
            'name': name,
            'description': '<p>%s</p>' % description,
            'reward_tokens': reward,
            'coop_specialization_id': specializations.get(specialization).id
                                      if specializations.get(specialization) else False,
            'manager_id': manager.id,
            # Решение 671 п. 7: автор даёт выбор. Чаще оба способа
            # платформы, у части — один, чтобы отбор по способу что-то
            # отбирал.
            'allowed_method_ids': [(6, 0, PLATFORM_METHOD_SETS[index % 3](methods))],
            # Срок в пределах полугода: при ста двадцати задачах шаг в
            # неделю уводил последние на два года вперёд, и раздел
            # выглядел бы планом до 2028 года.
            'deadline': fields.Date.add(fields.Date.context_today(Task),
                                        days=7 + (index * 11) % 180),
        }
        if task:
            # Состояние у существующей задачи не трогаем: её могли двигать
            # руками, показывая раздел, и откат этого при обновлении
            # модуля выглядел бы как потеря работы.
            task.write({k: v for k, v in values.items()
                        if k not in ('state', 'allowed_method_ids')})
            continue

        task = Task.create(dict(values, state='draft',
                                criterion_ids=_criteria(description, index)))
        created += 1

        if state == 'published':
            task.action_publish()
            continue

        # Задачи в работе и дальше: заявка, утверждение, сдача, приёмка —
        # проходятся теми же действиями, что и в жизни, а не проставлением
        # состояния. Иначе демо-данные разойдутся с логикой: у принятой
        # задачи не окажется ни исполнителя, ни начисленных токенов.
        task.action_publish()
        if not people:
            continue
        performer = people[index % len(people)]
        allowed = task.allowed_method_ids
        application = env['coop.bounty.application'].sudo().create({
            'task_id': task.id,
            'partner_id': performer.id,
            'method_id': allowed[index % len(allowed)].id,
            'message': 'Возьмусь, делал похожее.',
        })
        application.action_approve()
        _drive(task, state, index)

    created += load_extra_platform_tasks(env, Task, manager, methods, specializations, people)
    created += load_project_tasks(env, Task, methods, specializations)
    _demo_tasks_to_projects(env, Task, methods)
    load_bounty_flow(env, Task)
    # Просроченные — напоминание и снятие; сданные больше семи дней
    # назад — в спор: так, как это сделают задания по расписанию.
    Task._cron_executor_silence()
    Task._cron_open_disputes()
    involved = Task.search([('state', '=', 'accepted')])
    (involved.mapped('assignee_id') | involved.mapped('payer_id'))._coop_recompute_deal_stats()

    # Токены на балансы: без них продвижение объявления невозможно, и
    # кнопка в каталоге ресурсов всегда отказывала бы.
    Token = env['coop.token.transaction'].sudo()
    owners = Partner.search([('coop_is_participant', '=', True)], order='id', limit=40)
    topped = 0
    for index, partner in enumerate(owners):
        if partner.coop_token_balance:
            continue
        Token.create({
            'partner_id': partner.id,
            'amount': 200 + (index % 5) * 150,
            'kind': 'topup',
            'description': 'Пополнение баланса',
        })
        topped += 1

    _logger.info('Помощь проекту: задач создано %s, балансов пополнено %s',
                 created, topped)
