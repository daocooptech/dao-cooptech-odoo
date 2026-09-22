# -*- coding: utf-8 -*-
"""Фотографии участникам — по полу и по одному разу.

Часть людей заведена не каталогом, а справочными данными — те, на кого
ссылаются членство, сделка и учётная запись пайщика. Фотографии у них не
было, и на странице человека, в полосе «Друзья» и в составе организации
они выглядели серыми кружками с буквой.

Пустая карточка — это состояние, которое должно попадаться при проверке,
но не у четверти каталога сразу: тогда не видно, как выглядит полоса из
плиток с лицами, ради которой она и сделана.

Снимки раздаются по полу. Пол участника нигде не хранится, но у русских
ФИО он однозначно читается по отчеству: «…овна», «…евна», «…ична» —
женщина; «…ович», «…евич», «…ич» — мужчина. Отчества нет или оно
нерусское — снимок не трогаем: угадать пол по имени вроде «Ким Сергей»
нельзя, а поставить наугад — ровно та ошибка, которую чиним.

Снимки лежат в двух папках, `men` и `women`, и другого источника нет.
Прежде рядом лежал третий набор — семьдесят снимков из макета, которые
раздавались по списку в `people.json`. Список оказался случайным: из ста
человек шестидесяти одному достался снимок чужого пола, ребёнок или
клоунская рожа с накладными усами. Снимки разобраны по полу и перенесены
в те же две папки, негодные удалены — теперь набор один, и расходиться
ему не с чем.

Владелец 20 сентября 2026: «ты несколько раз уже поменял мне фото, верни
которое было». Его снимок теперь не раздаётся, а закреплён по имени —
`PINNED`; раздача такие карточки обходит стороной.
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

# Закреплённые снимки: имя участника → файл в `avatars`.
PINNED = {
    'Дашкевич Данил Игоревич': 'dashkevich.jpg',
}

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


def _stub(data):
    """Служебный значок вместо фотографии.

    Движок кладёт в карточку SVG с буквой — триста байт разметки.
    Поле при этом не пусто, и человек мимо раздачи проходит дважды:
    и как «фото есть», и как «чужое фото, не трогаем».
    """
    start = (data or b'')[:64].lstrip()
    return start.startswith(b'<?xml') or start.startswith(b'<svg')


def _our_photos():
    """Отпечаток файла → папка, в которой он лежит.

    По отпечатку раздаваемый снимок узнаётся в базе: своё фото,
    загруженное участником, в наборе не числится и остаётся на месте.
    """
    prints = {}
    for directory in (AVATAR_DIR, WOMEN_DIR, MEN_DIR):
        for name in _files(directory):
            path = os.path.join(directory, name)
            with open(path, 'rb') as handle:
                prints[hashlib.sha256(handle.read()).hexdigest()] = directory
    return prints


def _participants(env):
    """Люди, которым полагается лицо: участники и те, кто состоит в
    организациях. Организации сюда не попадают — у них знак, не лицо."""
    members = env['coop.membership'].sudo().search([]).mapped('partner_id')
    return env['res.partner'].sudo().search([
        ('is_company', '=', False),
        '|', ('coop_is_participant', '=', True), ('id', 'in', members.ids),
    ])


def ensure_faces(env):
    """Раздать лица и переставить те, что достались не тому полу.

    Один проход вместо двух: раздача и перестановка отличались только
    тем, пусто поле или нет, а расходились в том, что считать «нашим»
    снимком, — и на узле, где снимки уже стояли, второй проход перебирал
    их каждый раз заново. Владелец это и увидел: фотография на его
    странице менялась от выкатки к выкатке.
    """
    women, men = _files(WOMEN_DIR), _files(MEN_DIR)
    if not women or not men:
        _logger.info('Фотографии: наборы по полу не найдены в %s', AVATAR_DIR)
        return 0

    ours = _our_photos()
    handed_out = moved = pinned = 0

    for partner in _participants(env):
        file = PINNED.get(partner.name)
        if file:
            path = os.path.join(AVATAR_DIR, file)
            if os.path.exists(path):
                photo = _read(path)
                if partner.image_1920 != photo:
                    partner.image_1920 = photo
                    pinned += 1
            continue

        gender = coop_gender(partner.name)
        if gender not in ('w', 'm'):
            continue
        needed_item = WOMEN_DIR if gender == 'w' else MEN_DIR
        set_of = women if gender == 'w' else men

        raw_one = partner.image_1920
        if raw_one:
            data = base64.b64decode(raw_one)
            from_where = ours.get(hashlib.sha256(data).hexdigest())
            if from_where is None and not _stub(data):
                # Не из наших наборов — фотография самого участника.
                continue
            if from_where == needed_item:
                continue
            partner.image_1920 = _read(_pick(needed_item, set_of, partner.id))
            moved += 1
            continue

        partner.image_1920 = _read(_pick(needed_item, set_of, partner.id))
        handed_out += 1

    _logger.info('Фотографии: роздано %s, переставлено %s, закреплено %s',
                 handed_out, moved, pinned)
    return handed_out + moved + pinned
