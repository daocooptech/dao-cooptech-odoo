# -*- coding: utf-8 -*-
"""Названия без городов и рубрики по смыслу (задача 406, 11.11.2026).

Владелец 10.11: «почему молоковоз в названии город, везде города убери.
почему подраздел платежи и обязательные расходы?»

Загрузчики добирали объём до 100–200, дописывая к повторному названию
« — город», а потребностям проекта — « — проект — город». Город стоит
отдельным полем, проект виден на карточке; в названии это шум, и в
каталоге он читается как сбой. Копии одной строки при этом тоже не
годятся (правило объёма) — поэтому повтор различается не городом, а
содержанием: сроком, партией, назначением, форматом.

Рубрика: добор копировал строку-образец целиком, и «Молоковоз» вышел
финансовым объявлением в «Платежах и обязательных расходах». Чиним
двумя шагами: явная таблица для тех, кого не по чему сверить, и голос
большинства — если у одного названия почти все копии стоят в одной
рубрике, туда же идут и отбившиеся. Тип объявления выводится из рубрики.

Всё идемпотентно: второй прогон ничего не меняет.
"""
import collections
import logging
import re

_logger = logging.getLogger(__name__)

SEP = ' — '
# Не города, но стоят в названиях на месте города.
PLACES_EXTRA = {'Удалённо', 'Онлайн', 'Дистанционно'}

# Уточнения по содержанию — по модели, двумя рядами: первый (A) — кому
# или когда, второй (B) — в каком виде. Первая запись с названием
# остаётся как есть, следующие получают одно уточнение из A, потом из B,
# а когда и они кончились — пару «A, B». Пары внутри одного ряда не
# берутся: «для новичков, для фермеров» и «на год, на первый сезон»
# читаются как опечатка.
POOLS = {
    'coop.event': (
        ['открытый формат', 'для участников сети', 'для гостей', 'семейный формат',
         'с трансляцией', 'выездной формат', 'малый формат', 'большой сбор'],
        ['утренняя часть', 'вечерняя часть', 'день первый', 'день второй',
         'выходного дня', 'будний день'],
    ),
    'coop.program': (
        ['для сельских кооперативов', 'для жилищных кооперативов',
         'для потребительских обществ', 'для ремесленников', 'для фермеров',
         'для молодёжи', 'для председателей', 'для бухгалтеров кооперативов',
         'для новых пайщиков', 'для артелей', 'для кредитных кооперативов',
         'для городских сообществ'],
        ['интенсив', 'вечерний формат', 'весенний набор', 'осенний набор'],
    ),
    'coop.community': (
        ['обмен опытом', 'для начинающих', 'семейные хозяйства', 'взаимопомощь',
         'клуб выходного дня', 'молодёжное крыло', 'закупки вскладчину',
         'мастер-классы', 'наставничество', 'общий инструмент', 'сбыт продукции'],
        [],
    ),
    'coop.groupbuy': (
        ['весенняя закупка', 'осенняя закупка', 'под посевную', 'на зиму',
         'под уборочную', 'на сезон'],
        ['оптовая партия', 'вторая партия', 'от завода', 'с доставкой до склада',
         'малыми партиями', 'пробная партия'],
    ),
    'coop.auction': (
        ['повторные торги', 'срочный лот', 'весенний лот', 'осенний лот',
         'короткие торги', 'без резервной цены'],
        ['с доставкой', 'с осмотром на месте', 'с гарантией', 'предоплата 30 %',
         'в рассрочку', 'по договору'],
    ),
    'coop.project': (
        ['при школе', 'в частном секторе', 'на промзоне', 'у рынка',
         'при кооперативе', 'на выезде из города', 'в новом микрорайоне',
         'у трассы', 'при складе', 'в посёлке', 'на базе гаража'],
        ['вторая очередь'],
    ),
    'project.project': (
        ['второй этап', 'пилот', 'для филиала', 'на новом складе', 'обновление',
         'перенос данных', 'доработка'],
        [],
    ),
    'coop.vacancy': (
        ['на полный день', 'на неполный день', 'вахтой', 'на сезон', 'подработка',
         'в ночную смену', 'по выходным', 'на время монтажа'],
        ['с опытом от года', 'без опыта, обучим', 'с жильём', 'по договору подряда'],
    ),
    'coop.barter.offer': (
        ['в хорошем состоянии', 'после ремонта', 'почти новый', 'на запчасти'],
        ['с документами', 'с доставкой', 'самовывоз', 'с комплектом'],
    ),
}

# Потребности проекта и личные объявления — по типу, теми же двумя рядами.
RESOURCE_POOLS = {
    'labour': (
        ['1 неделя', '2 недели', '3 недели', '1 месяц', '2 месяца', '3 месяца',
         'на запуск', 'на пусконаладку'],
        ['по сменам', 'выездной', 'с опытом', 'в выходные', 'по вечерам',
         'по договору подряда', 'с инструментом', 'с проживанием', 'на объекте',
         'под ключ'],
    ),
    'financial': (
        ['на первый этап', 'на второй этап', 'на запуск', 'до открытия',
         'на первый сезон', 'на пусконаладку', 'на год', 'на полгода'],
        ['ежемесячно', 'разовый платёж', 'по договору', 'с отсрочкой',
         'через кооператив', 'первый взнос', 'безналично', 'поэтапно'],
    ),
    'material': (
        ['первая партия', 'на первый этап', 'на второй этап', 'на третий этап',
         'на пусконаладку', 'на запуск', 'на сезон', 'комплект на участок'],
        ['с доставкой на площадку', 'б/у подойдёт', 'под ключ', 'с запасом',
         'с документами', 'срочно', 'недорого', 'в наличии', 'самовывоз',
         'в рассрочку'],
    ),
}

# Учётные модели — город снимаем, копии не различаем: это не каталоги,
# а следы сделок, и одинаковая строка в двух сделках — норма.
# Товары — тоже: «Песок» в двух заказах — один и тот же песок.
STRIP_ONLY = ['coop.deal', 'coop.deal.line', 'coop.document',
              'coop.project.contribution', 'coop.farm.pool', 'product.template']

# Явные рубрики: у этих названий все копии стояли не там, сверять не с чем.
# Ключ — кусок названия в нижнем регистре, значение — лист справочника.
RUBRIC_BY_WORD = [
    ('молоковоз', 'Грузовики и автобусы'),
    ('шерсть овечья', 'Сырьё для ремёсел'),
    ('саженцы', 'Овощи и фрукты'),
    ('мёд разнотравье', 'Мёд и продукты пчеловодства'),
    ('сеялка', 'Сельхозтехника'),
    ('сварочный аппарат', 'Станки по дереву и металлу'),
    ('шредер для пластика', 'Станки по дереву и металлу'),
    ('расходные материалы для монтажа', 'Расходники для монтажа'),
    ('книжный фонд', 'Хобби и отдых'),
    ('ищу участок', 'Земельные участки'),
    ('обменяю участок', 'Земельные участки'),
    ('участок под', 'Земельные участки'),
    ('сдам гараж', 'Гаражи и машиноместа'),
]
FINANCIAL_LEAVES = {'Финансирование', 'Платежи и обязательные расходы'}
SERVICES_ROOT = 'Услуги и финансы'


def _places(env):
    names = set(PLACES_EXTRA)
    for model in ('res.partner', 'coop.resource'):
        if model in env and 'city' in env[model]._fields:
            env.cr.execute('SELECT DISTINCT city FROM %s WHERE city IS NOT NULL'
                           % env[model]._table)
            names.update(row[0].strip() for row in env.cr.fetchall() if row[0])
    if 'res.city' in env:
        names.update(env['res.city'].sudo().search([]).mapped('name'))
    return {n for n in names if n and len(n) < 40}


# Срок в названии: «2 недели», «1 месяц», «36 смен».
DURATION = re.compile(r'\d+\s*(недел[ьяи]|месяц(а|ев)?|смен[ыа]?|дн(я|ей)|день)', re.I)

# Номер копии « (4)», который старый добор ставил после города.
COPY_NO = re.compile(r'\s*\(\d+\)$')


def _strip(name, places, drop=()):
    parts = [COPY_NO.sub('', p) for p in (name or '').split(SEP)]
    kept = [parts[0]]
    for part in parts[1:]:
        head, _comma, tail = part.partition(',')
        if part.strip() in places or part.strip() in drop:
            continue
        if head.strip() in places:
            # «Пилорама — Омск, недорого»: город уходит, уточнение остаётся.
            kept[-1] = '%s, %s' % (kept[-1], tail.strip())
            continue
        kept.append(part)
    # «…, недорого, недорого» — повтор уточнения схлопываем; второй срок
    # после первого («, 1 месяц, 1 неделя») — тоже.
    bits = []
    for bit in SEP.join(kept).split(', '):
        if bits and bits[-1].strip() == bit.strip():
            continue
        if (bits and DURATION.fullmatch(bit.strip())
                and any(DURATION.search(b) for b in bits)):
            continue
        bits.append(bit)
    return ', '.join(bits).strip()


def _unique(group, base, pool, taken):
    """Названия для группы записей с одной основой: первая — как есть."""
    out = []
    have = {bit.strip() for bit in base.split(',')}
    first = [q for q in pool[0] if q not in have]
    second = [q for q in pool[1] if q not in have]
    if DURATION.search(base):
        # «Тестировщик, 1 месяц» — срок уже есть, второй («, 1 неделя») не нужен.
        first = [q for q in first if not DURATION.search(q)]
        second = [q for q in second if not DURATION.search(q)]
    combos = ([base] + ['%s, %s' % (base, q) for q in first + second]
              + ['%s, %s, %s' % (base, a, b) for a in first for b in second])
    it = iter(c for c in combos)
    for _record in group:
        for candidate in it:
            if candidate not in taken:
                taken.add(candidate)
                out.append(candidate)
                break
        else:
            out.append(None)
    return out


def _dedupe(env, model, places, pool_of, drop_of=None):
    Model = env[model].sudo().with_context(active_test=False, tracking_disable=True,
                                           mail_notrack=True)
    records = Model.search([], order='id')
    stripped = {}
    for record in records:
        drop = drop_of(record) if drop_of else ()
        stripped[record.id] = _strip(record.name, places, drop)
    # Записи, чьё название не меняется и не повторяется, держат его.
    # Трогаем только основы, у которых хоть одна запись несла город или
    # проект: прочие повторы — не эта задача, и штатные записи движка
    # («Внутренний» у проектов учёта) должны остаться как есть.
    touched = {stripped[r.id] for r in records if r.name != stripped[r.id]}
    taken = set()
    groups = collections.OrderedDict()
    for record in records:
        base = stripped[record.id]
        if base not in touched:
            taken.add(record.name)
            continue
        groups.setdefault(base, []).append(record)
    renamed = 0
    for base, group in groups.items():
        # Запись, у которой название уже совпадает с основой, идёт первой.
        group.sort(key=lambda r: (r.name != base, r.id))
        # Набор — по проектной записи, если она в группе есть: у потребностей
        # проектов копий больше, и короткого набора личных им не хватит.
        sample = next((r for r in group
                       if 'project_id' in r._fields and r.project_id), group[0])
        names = _unique(group, base, pool_of(sample), taken)
        for record, new in zip(group, names):
            if new and new != record.name:
                _set_name(record, new)
                renamed += 1
    return renamed


def _set_name(record, new):
    """Название — во всех языках: у проектов оно переводимое, и запись без
    языка обновила бы только английское значение."""
    if getattr(record._fields['name'], 'translate', False):
        for lang, _label in record.env['res.lang'].get_installed():
            record.with_context(lang=lang).name = new
    else:
        record.name = new


def _resource_pool(record):
    if not record.project_id:
        from . import load_spread
        word = (record.name or '').split(' ', 1)[0].lower()
        first = list(dict.fromkeys(load_spread._QUALIFIERS.get(word, [])
                                   + load_spread._DEFAULT_QUALIFIERS))
        return first, [q for q in ('с доставкой', 'по договору', 'с документами',
                                   'торг уместен', 'без посредников',
                                   'фото по запросу', 'можно частями')
                       if q not in first]
    return RESOURCE_POOLS.get(record.resource_type, RESOURCE_POOLS['material'])


def _project_bases(env, places):
    if 'coop.project' not in env:
        return set()
    return {_strip(n, places) for n in env['coop.project'].sudo().with_context(
        active_test=False).search([]).mapped('name') if n} | set(
        env['coop.project'].sudo().with_context(active_test=False).search([]).mapped('name'))


def uncity_names(env):
    places = _places(env)
    total = {}
    # Проекты — первыми: их названия сидят в названиях потребностей и пулов.
    old_projects = _project_bases(env, places)
    for model, pool in POOLS.items():
        if model not in env or 'name' not in env[model]._fields:
            continue
        total[model] = _dedupe(env, model, places, lambda r, p=pool: p)
    if 'coop.resource' in env:
        drops = old_projects | _project_bases(env, places)
        total['coop.resource'] = _dedupe(
            env, 'coop.resource', places, _resource_pool,
            lambda r, d=drops: d if r.project_id else ())
    drops = old_projects | _project_bases(env, places)
    for model in STRIP_ONLY:
        if model not in env:
            continue
        Model = env[model].sudo().with_context(active_test=False, tracking_disable=True,
                                               mail_notrack=True)
        changed = 0
        for record in Model.search([('name', 'like', SEP)]):
            if model == 'coop.farm.pool' and record.project_id:
                parts = _strip(record.name, places).split(SEP)
                new = SEP.join([record.project_id.name] + parts[1:])
            else:
                new = _strip(record.name, places,
                             drops if model == 'coop.project.contribution' else ())
            if new != record.name:
                _set_name(record, new)
                changed += 1
        total[model] = changed
    _logger.info('Названия без городов: %s', {k: v for k, v in total.items() if v})
    return total


def _leaf(env, name, cache):
    if name not in cache:
        cache[name] = env['coop.resource.category'].sudo().search(
            [('name', '=', name), ('parent_id', '!=', False)], limit=1)
    return cache[name]


def _root(category):
    while category.parent_id:
        category = category.parent_id
    return category


def fix_resource_rubrics(env):
    if 'coop.resource' not in env:
        return 0
    Resource = env['coop.resource'].sudo().with_context(
        active_test=False, tracking_disable=True, mail_notrack=True)
    records = Resource.search([], order='id')
    cache = {}
    moved = 0
    # 1. Явная таблица — когда сам лист в другом корне.
    for record in records:
        low = (record.name or '').lower()
        for word, leaf_name in RUBRIC_BY_WORD:
            if word in low:
                leaf = _leaf(env, leaf_name, cache)
                if leaf and _root(leaf) != _root(record.category_id):
                    record.category_id = leaf
                    moved += 1
                break
    # 2. Голос большинства по основе названия (до первой запятой и тире).
    def base(name):
        return (name or '').split(SEP)[0].split(',')[0].strip().lower()
    votes = collections.defaultdict(collections.Counter)
    for record in records:
        votes[base(record.name)][record.category_id.id] += 1
    for record in records:
        tally = votes[base(record.name)]
        total = sum(tally.values())
        top, n = tally.most_common(1)[0]
        if total >= 3 and n / total >= 0.6 and top and record.category_id.id != top:
            record.category_id = top
            moved += 1
    # 3. Тип — из рубрики: деньги, труд или вещь.
    retyped = 0
    for record in records:
        category = record.category_id
        if not category:
            continue
        if category.name in FINANCIAL_LEAVES:
            kind = 'financial'
        elif _root(category).name == SERVICES_ROOT:
            kind = 'labour'
        else:
            kind = 'material'
        if record.resource_type != kind:
            record.resource_type = kind
            retyped += 1
    _logger.info('Рубрики ресурсов: перенесено %s, тип поправлен у %s', moved, retyped)
    return moved, retyped


def tidy_all(env):
    rubrics = fix_resource_rubrics(env)
    names = uncity_names(env)
    return rubrics, names
