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


def _заглушка(данные):
    """Служебный значок вместо фотографии.

    Движок кладёт в карточку SVG с буквой — триста байт разметки.
    Поле при этом не пусто, и человек мимо раздачи проходит дважды:
    и как «фото есть», и как «чужое фото, не трогаем».
    """
    начало = (данные or b'')[:64].lstrip()
    return начало.startswith(b'<?xml') or начало.startswith(b'<svg')


def _наши_снимки():
    """Отпечаток файла → папка, в которой он лежит.

    По отпечатку раздаваемый снимок узнаётся в базе: своё фото,
    загруженное участником, в наборе не числится и остаётся на месте.
    """
    отпечатки = {}
    for directory in (AVATAR_DIR, WOMEN_DIR, MEN_DIR):
        for name in _files(directory):
            path = os.path.join(directory, name)
            with open(path, 'rb') as handle:
                отпечатки[hashlib.sha256(handle.read()).hexdigest()] = directory
    return отпечатки


def _участники(env):
    """Люди, которым полагается лицо: участники и те, кто состоит в
    организациях. Организации сюда не попадают — у них знак, не лицо."""
    члены = env['coop.membership'].sudo().search([]).mapped('partner_id')
    return env['res.partner'].sudo().search([
        ('is_company', '=', False),
        '|', ('coop_is_participant', '=', True), ('id', 'in', члены.ids),
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

    наши = _наши_снимки()
    роздано = переставлено = закреплено = 0

    for partner in _участники(env):
        файл = PINNED.get(partner.name)
        if файл:
            путь = os.path.join(AVATAR_DIR, файл)
            if os.path.exists(путь):
                снимок = _read(путь)
                if partner.image_1920 != снимок:
                    partner.image_1920 = снимок
                    закреплено += 1
            continue

        пол = coop_gender(partner.name)
        if пол not in ('w', 'm'):
            continue
        нужная = WOMEN_DIR if пол == 'w' else MEN_DIR
        набор = women if пол == 'w' else men

        сырой = partner.image_1920
        if сырой:
            данные = base64.b64decode(сырой)
            откуда = наши.get(hashlib.sha256(данные).hexdigest())
            if откуда is None and not _заглушка(данные):
                # Не из наших наборов — фотография самого участника.
                continue
            if откуда == нужная:
                continue
            partner.image_1920 = _read(_pick(нужная, набор, partner.id))
            переставлено += 1
            continue

        partner.image_1920 = _read(_pick(нужная, набор, partner.id))
        роздано += 1

    _logger.info('Фотографии: роздано %s, переставлено %s, закреплено %s',
                 роздано, переставлено, закреплено)
    return роздано + переставлено + закреплено
