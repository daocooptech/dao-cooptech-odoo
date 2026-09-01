# -*- coding: utf-8 -*-
"""Знаки организаций и ресурсов.

Основной набор — настоящие эмблемы существовавших предприятий с
Викисклада, только под свободными лицензиями (общественное достояние и
CC0). Лежат в `static/img/marks`, происхождение каждого файла записано в
`MANIFEST.json` рядом. Их 107 на без малого две сотни организаций,
поэтому остальным достаётся знак, нарисованный здесь.

Про то, чего в наборе нет. Логотипы действующих компаний и работы
дизайнеров с портфолио-сайтов не годятся: «организации уже нет» прав не
снимает — авторское право на изображение живёт десятилетиями и переходит
к правопреемникам, а товарный знак может быть продлён. Свободная лицензия
снимает вопрос целиком, и проверяется она машинно при отборе.

Нарисованный знак собирается из символа и подложки. Символы взяты из
Tabler Icons — набора под лицензией MIT, которая прямо разрешает
коммерческое использование и изменение (см. `icons/LICENSE`, удалять его
нельзя).

Символ подбирается по роду занятий: у сельхозкооператива — росток, у
кредитного — монета, у ремесленной артели — молоток. Не украшение: в
каталоге из двухсот плиток по знаку видно, чем организация занимается,
ещё до того, как прочитано название. Если род занятий неизвестен, знак
выбирается по хэшу названия — детерминированно, чтобы одна и та же
организация всегда выглядела одинаково.
"""
import base64
import hashlib
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(HERE, 'icons')
MARK_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img', 'marks')

# Палитра платформы. Цвета те же, что в оформлении, поэтому каталог не
# распадается на разноцветную мозаику: знаки узнаваемо принадлежат одной
# системе, различаясь оттенком, а не яркостью.
PALETTE = [
    ('#146b64', '#e3efed'),   # бирюзовый на светлом
    ('#0e4f4a', '#dceae8'),   # тёмно-бирюзовый
    ('#c98a2b', '#f7ecd9'),   # золотой на песочном
    ('#8a5c14', '#f3e4cd'),   # тёмно-золотой
    ('#4a4a44', '#f2f2ee'),   # графит на сером
    ('#14171a', '#ececeA'),   # чернильный
]

# Символ по роду занятий. Ключ — подстрока названия специализации или
# сферы деятельности; проверяются по порядку, поэтому частное стоит
# раньше общего.
BY_SPECIALIZATION = [
    ('агроном', 'plant-2'),
    ('пчелов', 'beehive'),
    ('ветеринар', 'pig'),
    ('сельск', 'tractor'),
    ('повар', 'bread'),
    ('кондитер', 'bread'),
    ('продавец', 'building-store'),
    ('розничн', 'shopping-cart'),
    ('закуп', 'packages'),
    ('склад', 'building-warehouse'),
    ('логист', 'truck-delivery'),
    ('транспорт', 'truck-delivery'),
    ('автослесар', 'car'),
    ('автосервис', 'car'),
    ('автомоб', 'car'),
    ('сварщик', 'flame'),
    ('сварочн', 'flame'),
    ('камен', 'bulldozer'),
    ('бетон', 'bulldozer'),
    ('прораб', 'building-factory-2'),
    ('строительн', 'building-factory-2'),
    ('архитектор', 'building-community'),
    ('недвижим', 'home-2'),
    ('столяр', 'wood'),
    ('плотник', 'wood'),
    ('лес', 'trees'),
    ('слесар', 'tools'),
    ('сантехник', 'droplet'),
    ('электро', 'antenna-bars-5'),
    ('швея', 'shirt'),
    ('закройщик', 'shirt'),
    ('ремесл', 'hammer'),
    ('промысл', 'hammer'),
    ('гончар', 'paint'),
    ('дизайн', 'paint'),
    ('художник', 'paint'),
    ('фото', 'camera'),
    ('видео', 'camera'),
    ('программир', 'device-laptop'),
    ('разработ', 'device-laptop'),
    ('аналитик', 'device-laptop'),
    ('data', 'device-laptop'),
    ('маркетинг', 'antenna-bars-5'),
    ('бухгалт', 'coin'),
    ('финанс', 'coin'),
    ('юрис', 'scale-outline'),
    ('право', 'scale-outline'),
    ('препода', 'school'),
    ('репетитор', 'school'),
    ('образован', 'school'),
    ('перевод', 'book'),
    ('медсестр', 'stethoscope'),
    ('фельдшер', 'stethoscope'),
    ('медицин', 'bandage'),
    ('массаж', 'heart-handshake'),
    ('косметолог', 'heart-handshake'),
    ('тренер', 'heart-handshake'),
    ('охранник', 'certificate'),
    ('контролёр', 'certificate'),
    ('hr', 'users'),
    ('персонал', 'users'),
    ('офис', 'briefcase'),
    ('менеджер', 'briefcase'),
    ('консультант', 'briefcase'),
    ('руководител', 'briefcase'),
    ('горный', 'mountain'),
    ('инженер', 'building-factory-2'),
    ('технолог', 'building-factory-2'),
    ('флорист', 'plant-2'),
    ('декоратор', 'plant-2'),
    ('домработ', 'home-2'),
    ('няня', 'home-2'),
    ('администратор', 'briefcase'),
    ('гостиниц', 'building-community'),
]

# Запасные символы: подбираются по хэшу названия, когда род занятий не
# известен. Нейтральные, без привязки к отрасли.
FALLBACK = ['building-community', 'users', 'heart-handshake', 'certificate',
            'packages', 'recycle', 'briefcase', 'building-bank']

_cache = {}


def _icon_body(name):
    """Содержимое иконки без обёртки <svg>.

    Иконки Tabler нарисованы обводкой по сетке 24×24 и красятся
    currentColor. Вынимаем внутренности, чтобы вставить их в свою
    подложку и задать цвет самим.
    """
    if name in _cache:
        return _cache[name]
    path = os.path.join(ICON_DIR, '%s.svg' % name)
    if not os.path.exists(path):
        _cache[name] = ''
        return ''
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    inner = re.search(r'<svg[^>]*>(.*)</svg>', text, re.S)
    body = inner.group(1).strip() if inner else ''
    # Иконки набора содержат прозрачный прямоугольник-подложку — он нам
    # мешает: своя подложка уже есть.
    body = re.sub(r'<path\s+stroke="none"[^/]*/>', '', body)
    _cache[name] = body
    return body


def _pick_icon(activity, name):
    if activity:
        low = activity.lower()
        for needle, icon in BY_SPECIALIZATION:
            if needle in low:
                return icon
    seed = int(hashlib.sha256(name.encode('utf-8')).hexdigest()[:8], 16)
    return FALLBACK[seed % len(FALLBACK)]


def _colors(name, shift=0):
    seed = int(hashlib.sha256(name.encode('utf-8')).hexdigest()[:8], 16)
    return PALETTE[(seed + shift) % len(PALETTE)]


def _letter(name):
    """Буква знака — из собственного имени, а не из правовой формы.

    У «ООО «Мириталь»» это «М»: иначе половина каталога оказалась бы под
    буквой «О», а вторая половина под «П».
    """
    quoted = re.search(r'[«"]\s*(\S)', name)
    return (quoted.group(1) if quoted else name.strip()[:1]).upper()


def _svg(bg, inner):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" '
            'viewBox="0 0 256 256"><rect width="256" height="256" fill="%s"/>%s'
            '</svg>') % (bg, inner)


def emblem(name, activity=None):
    """Знак: символ рода занятий на фирменной подложке.

    Символ рисуется в центре и занимает чуть больше трети стороны — так
    он читается и в плитке каталога, и в миниатюре списка.
    """
    fg, bg = _colors(name)
    body = _icon_body(_pick_icon(activity, name))
    # Иконка 24×24 масштабируется до 112 и ставится в центр поля 256×256.
    glyph = ('<g transform="translate(72 72) scale(%.3f)" fill="none" '
             'stroke="%s" stroke-width="1.7" stroke-linecap="round" '
             'stroke-linejoin="round">%s</g>') % (112 / 24.0, fg, body)
    return base64.b64encode(_svg(bg, glyph).encode('utf-8'))


def monogram(name, activity=None):
    """Знак-буква с символом рода занятий над ней.

    Буква даёт узнаваемость — организацию ищут по названию, — а символ
    подсказывает занятие. Символ приглушён: он подпись к букве, а не
    второй знак рядом с ней.
    """
    fg, bg = _colors(name, shift=1)
    body = _icon_body(_pick_icon(activity, name))
    glyph = ('<g transform="translate(114 44) scale(%.3f)" fill="none" '
             'stroke="%s" stroke-width="1.9" stroke-linecap="round" '
             'stroke-linejoin="round" opacity="0.5">%s</g>') % (56 / 24.0, fg, body)
    text = ('<text x="128" y="182" fill="%s" font-family="Manrope, sans-serif" '
            'font-size="86" font-weight="700" text-anchor="middle">%s</text>'
            ) % (fg, _letter(name))
    return base64.b64encode(_svg(bg, glyph + text).encode('utf-8'))


def _marks():
    """Список настоящих эмблем, отсортированный для повторяемости.

    Порядок фиксированный: иначе при каждой пересборке стенда знаки
    разъезжались бы по другим организациям, и по скриншоту вчерашнего дня
    нельзя было бы найти запись.
    """
    if 'marks' not in _cache:
        try:
            files = sorted(f for f in os.listdir(MARK_DIR) if f.endswith('.png'))
        except OSError:
            files = []
        _cache['marks'] = files
    return _cache['marks']


class MarkAllocator:
    """Раздатчик настоящих эмблем — по одной на организацию.

    По порядку, а не по хэшу: хэш раздал бы один и тот же знак нескольким
    организациям и оставил бы часть набора неиспользованной. Один
    раздатчик на весь прогон загрузчика, иначе каталог и заполненные
    карточки разберут одни и те же файлы дважды.
    """

    def __init__(self):
        self._files = _marks()
        self._index = 0

    def next(self):
        """Следующий файл или None, когда набор кончился."""
        if self._index >= len(self._files):
            return None
        path = os.path.join(MARK_DIR, self._files[self._index])
        self._index += 1
        return path

    @property
    def used(self):
        return self._index

    @property
    def total(self):
        return len(self._files)
