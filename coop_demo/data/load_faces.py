# -*- coding: utf-8 -*-
"""Фотографии участникам — по полу.

Часть людей заведена не каталогом, а справочными данными — те, на кого
ссылаются членство, сделка и учётная запись пайщика. Фотографии у них не
было, и на странице человека, в полосе «Друзья» и в составе организации
они выглядели серыми кружками с буквой.

Пустая карточка — это состояние, которое должно попадаться при проверке,
но не у четверти каталога сразу: тогда не видно, как выглядит полоса из
плиток с лицами, ради которой она и сделана.

Снимки раздаются по полу. Прежде они лежали одной папкой и доставались
по остатку номера записи — и половине женщин доставалось мужское лицо.
Владелец 20 сентября 2026 наткнулся на это в своих друзьях: «у меня в
друзьях белова инна сергеевна с фото мужчины».

Пол участника нигде не хранится, но у русских ФИО он однозначно читается
по отчеству: «…овна», «…евна», «…ична» — женщина; «…ович», «…евич»,
«…ич» — мужчина. Отчества нет или оно нерусское — снимок не трогаем:
угадать пол по имени вроде «Ким Сергей» нельзя, а поставить наугад —
ровно та ошибка, которую чиним.
"""
import base64
import hashlib
import logging
import os

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
AVATAR_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img', 'avatars')
WOMEN_DIR = os.path.join(AVATAR_DIR, 'women')
MEN_DIR = os.path.join(AVATAR_DIR, 'men')

# Окончания отчеств. «…ович» стоит раньше «…ич» только для читаемости:
# проверка идёт по кортежу целиком, и «Игоревич» подходит под оба —
# важно, что оба мужские.
WOMAN_ENDINGS = ('овна', 'евна', 'инична', 'ична')
MAN_ENDINGS = ('ович', 'евич', 'ич')


def _files(directory):
    if not os.path.isdir(directory):
        return []
    return sorted(name for name in os.listdir(directory)
                  if name.lower().endswith(('.jpg', '.jpeg', '.png')))


def coop_gender(name):
    """Пол по отчеству: 'w', 'm' или None, если не читается."""
    parts = (name or '').strip().split()
    if len(parts) < 3:
        return None
    patronymic = parts[2].lower()
    if patronymic.endswith(WOMAN_ENDINGS):
        return 'w'
    if patronymic.endswith(MAN_ENDINGS):
        return 'm'
    return None


def _pick(directory, files, partner_id):
    """Снимок по остатку номера записи.

    Не случайно: повторный прогон даёт тем же людям те же лица, и снимки
    на экране не пляшут от пересборки к пересборке.
    """
    return os.path.join(directory, files[partner_id % len(files)])


def _read(path):
    with open(path, 'rb') as handle:
        return base64.b64encode(handle.read())


def _заглушка(данные):
    """Служебный значок вместо фотографии.

    Движок кладёт в карточку SVG с буквой — триста байт разметки.
    Поле при этом не пусто, и человек мимо раздачи проходит дважды:
    и как «фото есть», и как «чужое фото, не трогаем».
    """
    начало = (данные or b'')[:64].lstrip()
    return начало.startswith(b'<?xml') or начало.startswith(b'<svg')


def _hashes(directory):
    """Отпечатки файлов папки — чтобы узнать раздаваемый снимок в базе."""
    отпечатки = {}
    for name in _files(directory):
        path = os.path.join(directory, name)
        with open(path, 'rb') as handle:
            отпечатки[hashlib.sha256(handle.read()).hexdigest()] = path
    return отпечатки


def load_faces(env):
    """Раздать фотографии участникам без изображения."""
    women, men = _files(WOMEN_DIR), _files(MEN_DIR)
    if not women or not men:
        _logger.info('Фотографии: наборы по полу не найдены в %s', AVATAR_DIR)
        return 0

    Partner = env['res.partner'].sudo()
    members = env['coop.membership'].sudo().search([]).mapped('partner_id')
    without = Partner.search([
        ('id', 'in', members.ids),
        ('is_company', '=', False),
        ('image_1920', '=', False),
    ])

    given = 0
    for partner in without:
        пол = coop_gender(partner.name)
        if пол == 'w':
            path = _pick(WOMEN_DIR, women, partner.id)
        elif пол == 'm':
            path = _pick(MEN_DIR, men, partner.id)
        else:
            continue
        partner.image_1920 = _read(path)
        given += 1

    _logger.info('Фотографии: выдано %s из %s участников', given, len(members))
    return given


def regender_faces(env):
    """Переставить снимки тем, кому достался чужой пол.

    Трогаем только те карточки, где стоит снимок из наших наборов —
    узнаём его по отпечатку файла. Своё фото, загруженное человеком,
    остаётся на месте: перебрать его значило бы стереть то, что участник
    выбрал сам.
    """
    women, men = _files(WOMEN_DIR), _files(MEN_DIR)
    if not women or not men:
        return 0

    наши = {}
    for directory in (AVATAR_DIR, WOMEN_DIR, MEN_DIR):
        наши.update(_hashes(directory))

    Partner = env['res.partner'].sudo()
    people = Partner.search([('is_company', '=', False),
                             ('image_1920', '!=', False)])
    переставлено = 0
    for partner in people:
        пол = coop_gender(partner.name)
        if пол not in ('w', 'm'):
            continue
        снимок = partner.image_1920
        if not снимок:
            continue
        сырой = base64.b64decode(снимок)
        отпечаток = hashlib.sha256(сырой).hexdigest()
        текущий = наши.get(отпечаток)
        if not текущий and not _заглушка(сырой):
            # Не из наших наборов — фотография самого участника, не трогаем.
            continue
        нужная = WOMEN_DIR if пол == 'w' else MEN_DIR
        if текущий and os.path.dirname(текущий) == нужная:
            continue
        path = _pick(нужная, women if пол == 'w' else men, partner.id)
        partner.image_1920 = _read(path)
        переставлено += 1

    _logger.info('Фотографии: переставлено по полу — %s', переставлено)
    return переставлено
