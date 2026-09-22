# -*- coding: utf-8 -*-
"""Снимки каталогам — одним проходом и с переклейкой неверных.

Зачем понадобилось. Каждый загрузчик ставил снимок сам и только там, где
поле пусто. Пока правила не менялись, это работало; стоило правилу
появиться или исправиться — старые записи оставались с тем, что им
досталось при первом прогоне. Пересчёт боевой базы 20 сентября 2026
показал, сколько от этого накопилось:

* 2102 записи без снимка вовсе — из них 1375 под названиями, к которым
  правила не было (крепёж, кабель, топливо, страхование, собрания);
* десяток записей с чужим снимком из самой первой закачки — у
  «Бетономешалки на 180 л» стояла морковь, у «Лесов строительных» —
  осенний лес. Именно это владелец и увидел: «в потребностях у
  бетономешалки картинка моркови»;
* вакансии и предложения навыка со снимком из макета, где он проставлен
  наугад: у «Швеи» сварка, у «Повара» столярный цех.

Что делает. Идёт по каталогам и для каждой записи считает, какой снимок
ей полагается: у вакансии и навыка — по роду занятий, у остального — по
названию. Дальше три случая:

* поле пусто — ставит;
* стоит снимок из наших наборов, но не тот, что полагается, — меняет;
* стоит снимок не из наборов — меняет: в наполнении своих снимков ни у
  кого нет, а этот пришёл из первой закачки и не совпадает с названием.

Лица участников этим проходом не трогаются: там своё правило и свой
разбор — `load_faces`.
"""
import base64
import hashlib
import logging
import os
import zlib

from . import emblems, load_resources, photos, professions

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img')

# Каталоги, которым снимок положен: модель, поле снимка, поле
# специализации (если у записи есть род занятий) и признак «переклеивать
# ли стоящий снимок».
CATALOGS = (
    ('coop.vacancy', 'image_1920', 'coop_specialization_id', True),
    ('coop.skill.offer', 'image_1920', 'coop_specialization_id', True),
    ('coop.resource', 'image_1920', None, True),
    ('coop.intangible', 'image_1920', None, True),
    ('coop.event', 'image_1920', None, True),
    ('coop.program', 'image_1920', None, True),
    ('coop.groupbuy', 'image_1920', None, True),
    # У сделок и аукционов снимок хранится сразу малым, и движок
    # пережимает его при записи: отпечаток вложения перестаёт совпадать
    # с файлом набора, и сверка каждый раз считает снимок чужим. Таким
    # каталогам снимок ставится только в пустое поле — иначе каждый
    # прогон переклеивал пятьсот записей заново.
    ('coop.deal', 'image_512', None, False),
    ('coop.auction', 'image_512', None, False),
    ('coop.warehouse.offer', 'image_1920', None, True),
)


def _prints():
    """Отпечаток файла → путь, по всем нашим наборам снимков.

    Отпечаток — sha1, как у движка: вложение хранит `checksum` того же
    вида, и по нему видно, какой файл стоит у записи, **не читая самого
    снимка**. Читать было нельзя: проход по трём тысячам записей
    поднимал в память по сотне килобайт на каждую и заканчивался
    MemoryError на боевой, где памяти гигабайт на всё вместе с базой.
    """
    table = {}
    for dirpath, _dirs, names in os.walk(IMG_DIR):
        for name in names:
            if not name.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            path = os.path.join(dirpath, name)
            with open(path, 'rb') as fh:
                table[hashlib.sha1(fh.read()).hexdigest()] = path
    return table


def _good_photos(env, model, field):
    """Номер записи → отпечаток снимка, который у неё стоит.

    Спрашиваем вложения, а не поле записи: у поля изображение приходит
    целиком, а нам нужен только отпечаток. Одним запросом на каталог
    вместо тысячи чтений.
    """
    attachments = env['ir.attachment'].sudo().search_read(
        [('res_model', '=', model), ('res_field', '=', field)],
        ['res_id', 'checksum', 'description'])
    return {att['res_id']: (att['checksum'], att['description'] or '')
            for att in attachments}


def _fit_for(name, specialization):
    """Снимки, которые записи подходят: путь на диске → отпечаток.

    Не один снимок, а все допустимые: у предмета есть варианты
    (`cement-bag.jpg`, `cement-bag-2.jpg`), у занятия — несколько
    снимков. Пока стоит любой из них, менять нечего: иначе каждый прогон
    переставлял бы карточки с места на место.
    """
    paths = []
    if specialization:
        paths = [os.path.join(IMG_DIR, p) for p in professions.files(specialization)]
    if not paths:
        rule = load_resources._photo_by_name(name or '')
        if rule:
            paths = [os.path.join(photos.PHOTO_DIR, att)
                    for att in photos._variants(rule)]
    return [p for p in paths if os.path.exists(p)]


def _pick(name, specialization):
    """Путь и содержимое снимка: сначала род занятий, потом название."""
    if specialization:
        fit = professions.files(specialization)
        if fit:
            number = zlib.crc32((name or '').encode('utf-8')) % len(fit)
            path = os.path.join(IMG_DIR, fit[number])
            with open(path, 'rb') as fh:
                return path, base64.b64encode(fh.read())
    rule = load_resources._photo_by_name(name or '')
    if rule:
        options = photos._variants(rule)
        if options:
            number = zlib.crc32((name or '').encode('utf-8')) % len(options)
            path = os.path.join(photos.PHOTO_DIR, options[number])
            with open(path, 'rb') as fh:
                return path, base64.b64encode(fh.read())
    return None, None


def ensure_photos(env):
    """Проставить и переклеить снимки во всех каталогах."""
    ours = _prints()
    total = {'поставлено': 0, 'переклеено': 0, 'знаком': 0}

    for model, field, spec_field, reglue in CATALOGS:
        if model not in env:
            continue
        Model = env[model].sudo()
        if field not in Model._fields:
            continue
        cost = _good_photos(env, model, field)
        placed = reglued = with_mark = 0
        for account, record in enumerate(Model.search([])):
            # Кэш ORM держит всё прочитанное; на трёх тысячах записей
            # этого хватает, чтобы съесть память целиком. Сбрасываем
            # часто и мелко.
            if account and not account % 50:
                env.invalidate_all()
            # Savepoint на запись: PostgreSQL обрывает транзакцию на
            # первой ошибке, и одна негодная запись тихо отменила бы все
            # снимки этого прогона.
            with env.cr.savepoint():
                specialization = ''
                if spec_field and spec_field in record._fields:
                    value = record[spec_field]
                    specialization = value.display_name if value else ''
                fit = _fit_for(record.name, specialization)
                print_one, from_where = cost.get(record.id, (None, ''))
                current = bool(print_one or from_where)

                if current and not reglue:
                    continue
                if current and fit:
                    # Сначала по метке источника: движок пережимает
                    # снимок при записи, и отпечаток вложения перестаёт
                    # совпадать с отпечатком файла. Метка переживает
                    # пережатие, а отпечаток — нет, и без неё каждый
                    # прогон переклеивал полторы сотни записей заново.
                    if from_where and from_where in fit:
                        continue
                    if_ours = ours.get(print_one)
                    if if_ours and if_ours in fit:
                        continue

                path, photo = _pick(record.name, specialization)
                if photo:
                    record.write({field: photo})
                    # Движок пережимает снимок при записи — отпечаток в
                    # базе не совпадает с отпечатком файла, и следующий
                    # прогон считал бы его чужим и переклеивал заново.
                    # Запоминаем отпечаток уже уложенного: набор наших
                    # снимков дополняется по ходу дела.
                    record.flush_recordset()
                    attachment = env['ir.attachment'].sudo().search([
                        ('res_model', '=', model), ('res_field', '=', field),
                        ('res_id', '=', record.id)], limit=1)
                    if attachment:
                        attachment.description = path
                    if current:
                        reglued += 1
                    else:
                        placed += 1
                    continue

                if not current:
                    # Предмет не опознан — знак организации честнее
                    # чужой фотографии.
                    gender_form = specialization or record.name
                    record.write({field: emblems.emblem(record.name, gender_form)})
                    with_mark += 1

        _logger.info('Снимки %s: поставлено %s, переклеено %s, знаком %s',
                     model, placed, reglued, with_mark)
        total['поставлено'] += placed
        total['переклеено'] += reglued
        total['знаком'] += with_mark

    _logger.info('Снимки каталогов: поставлено %(поставлено)s, '
                 'переклеено %(переклеено)s, знаком %(знаком)s', total)
    return total['поставлено'] + total['переклеено'] + total['знаком']


def ensure_marks(env):
    """Знак каждой организации — из набора эмблем, и по одному разу.

    Знаки раздавались по порядку и только тем, у кого поле пусто. Пока
    набор не менялся, этого хватало; но часть файлов оказалась не
    знаками вовсе — спутниковый снимок, фотография здания, разворот
    удостоверения, — и, когда их убрали из набора, у организаций они
    остались: раздача до заполненного поля не доходит.

    Здесь наоборот: организация со знаком, которого в наборе больше нет,
    получает следующий свободный. Занятые считаются по самим карточкам,
    чтобы один знак не достался двоим.
    """
    files = [name for name in sorted(os.listdir(emblems.MARK_DIR))
             if name.lower().endswith('.png')] if os.path.isdir(emblems.MARK_DIR) else []
    if not files:
        return 0
    prints = {}
    for name in files:
        path = os.path.join(emblems.MARK_DIR, name)
        with open(path, 'rb') as fh:
            prints[hashlib.sha1(fh.read()).hexdigest()] = name

    Partner = env['res.partner'].sudo()
    organizations = Partner.search([('is_company', '=', True)], order='id')

    # Отпечаток из вложения, а не из самого поля: знаков две сотни, и
    # читать каждый ради сверки незачем — движок уже хранит `checksum`.
    cost = _good_photos(env, 'res.partner', 'image_1920')

    taken = set()
    is_needed = []
    for org in organizations:
        print_one, from_where = cost.get(org.id, (None, ''))
        # Метка источника надёжнее отпечатка: знак мог быть пережат при
        # записи. Без разбора пары сверка не находила ничего — и раздача
        # переставляла знаки всем двумстам организациям на каждом прогоне.
        name = os.path.basename(from_where) if from_where else prints.get(print_one)
        if name and name in files and name not in taken:
            taken.add(name)
        else:
            is_needed.append(org)

    free = [name for name in files if name not in taken]
    granted = 0
    for account, (org, name) in enumerate(zip(is_needed, free)):
        if account and not account % 50:
            env.invalidate_all()
        path = os.path.join(emblems.MARK_DIR, name)
        with open(path, 'rb') as fh:
            org.image_1920 = base64.b64encode(fh.read())
        org.flush_recordset()
        attachment = env['ir.attachment'].sudo().search([
            ('res_model', '=', 'res.partner'), ('res_field', '=', 'image_1920'),
            ('res_id', '=', org.id)], limit=1)
        if attachment:
            attachment.description = path
        granted += 1

    _logger.info('Знаки организаций: выдано %s, без знака осталось %s',
                 granted, max(0, len(is_needed) - len(free)))
    return granted
