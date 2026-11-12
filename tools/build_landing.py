#!/usr/bin/env python3
"""Сборка лендинга из макета дизайн-артефакта «Лендинг ДАО КООПТЕХ».

Макет — `project/Main.dc.html` артефакта
https://claude.ai/artifact/GTTCWiFifdoGD6ubiNXjqF: стили, разметка с
привязками `{{…}}`, `sc-for`, `sc-if` и логика `renderVals()`. Скрипт
раскладывает их по файлам модуля `coop_website` без пересказа: стили —
как есть, разметка и логика — строкой в JS, который отрисовывает
`static/src/landing/runtime.js`. Так новая версия макета переносится
одним запуском, а не правкой руками.

Запуск (из `coop-addons`):

    python tools/build_landing.py <папка project макета> [<папка снимков>]

Снимки экранов макета (`/_blob/<id>`) кладутся в
`coop_website/static/src/img/landing/<id>.jpg`; папка снимков — там, куда
их сохранило чтение ассетов артефакта.
"""
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.join(os.path.dirname(HERE), 'coop_website')
OUT = os.path.join(MODULE, 'static', 'src', 'landing')
IMG = os.path.join(MODULE, 'static', 'src', 'img', 'landing')
IMG_URL = '/coop_website/static/src/img/landing/'
FONTS = '/coop_theme/static/src/fonts/'
LOGO_URL = '/coop_theme/static/src/img/cooptech-logo.png'

# Знак платформы. В макете лендинга вместо него заглушка — буквы «DC» в
# тёмном квадрате; на лендинг идёт тот же логотип, что в шапке платформы.
MARK_RE = re.compile(r'<span class="mark">[^<]*</span>')
MARK = '<img class="mark-logo" src="%s" alt="cooptech"/>' % LOGO_URL
# Лого нарисовано для тёмной темы: чёрная подложка, белые буквы. В
# светлой теме — инверсия (в файле два цвета, без полутонов), в тёмной
# (`.root.dark`) она снимается — как `.o_coop_logo` в coop_theme.
MARK_CSS = ('.mark-logo{display:block;height:28px;width:auto;border-radius:4px;'
            'filter:invert(1)}\n.root.dark .mark-logo{filter:none}')

FONT_FACES = [
    ('Inter', 400, 'inter-400'), ('Inter', 500, 'inter-500'), ('Inter', 700, 'inter-700'),
    ('Manrope', 500, 'manrope-500'), ('Manrope', 600, 'manrope-600'),
    ('Manrope', 700, 'manrope-700'), ('Manrope', 800, 'manrope-800'),
    ('JetBrains Mono', 500, 'jetbrains-mono'), ('JetBrains Mono', 700, 'jetbrains-mono'),
]
CYR = 'U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116'
LAT = 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+20BD,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD'


def font_css():
    out = []
    for family, weight, stem in FONT_FACES:
        for sub, rng in (('cyrillic', CYR), ('latin', LAT)):
            out.append(
                "@font-face{font-family:'%s';font-style:normal;font-weight:%s;"
                "font-display:swap;src:url(%s%s-%s.woff2) format('woff2');unicode-range:%s}"
                % (family, weight, FONTS, stem, sub, rng))
    return '\n'.join(out)


def cut(text, start, end, what):
    i = text.find(start)
    j = text.find(end, i + len(start))
    if i < 0 or j < 0:
        sys.exit('В макете не найден блок «%s»' % what)
    return text[i + len(start):j]


def localize(text):
    """Адреса макета → адреса узла. Макет ссылается на daocoop.tech, а
    боевая сейчас отвечает и по IP: абсолютные ссылки увели бы посетителя
    на неработающий домен."""
    text = text.replace("'https://daocoop.tech/web/signup?src=invite",
                        "location.origin + '/web/signup?src=invite")
    text = text.replace('href="https://daocoop.tech"', 'href="{{contactHref}}"')
    text = text.replace('https://daocoop.tech/', '/')
    text = re.sub(r'/_blob/([0-9a-f]{32})', IMG_URL + r'\1.jpg', text)
    left = [m.start() for m in re.finditer(r'https?://daocoop\.tech', text)]
    if left:
        sys.exit('Осталась абсолютная ссылка на daocoop.tech: %s' % text[left[0]:left[0] + 80])
    return text


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    with open(os.path.join(src, 'Main.dc.html'), encoding='utf-8') as fh:
        html = fh.read()

    helmet = cut(html, '<helmet>', '</helmet>', 'helmet')
    css = cut(helmet, '<style>', '</style>', 'style')
    markup = cut(html, '</helmet>', '</x-dc>', 'разметка').strip()
    script = cut(html, 'data-dc-script', '</script>', 'логика')
    logic = script[script.index('class Component'):].strip()

    blobs = sorted(set(re.findall(r'/_blob/([0-9a-f]{32})', html)))
    markup, logic = localize(markup), localize(logic)
    markup, found = MARK_RE.subn(MARK, markup)
    if not found:
        sys.exit('В макете не найден знак платформы (<span class="mark">)')

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'landing.css'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('/* Собрано tools/build_landing.py из макета лендинга, руками не править. */\n')
        fh.write(font_css() + '\n' + localize(css).strip() + '\n' + MARK_CSS + '\n')
    with open(os.path.join(OUT, 'landing_page.js'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('/** @odoo-module ignore */\n')
        fh.write('/* Собрано tools/build_landing.py из макета лендинга, руками не править. */\n')
        fh.write('(function () {\n"use strict";\n')
        fh.write('const DCLogic = window.CoopLandingRuntime.DCLogic;\n')
        fh.write(logic + '\n')
        fh.write('window.CoopLandingRuntime.mount(%s, Component);\n' % json.dumps(markup, ensure_ascii=False))
        fh.write('})();\n')

    if len(sys.argv) > 2:
        os.makedirs(IMG, exist_ok=True)
        for blob in blobs:
            path = os.path.join(sys.argv[2], blob + '.jpg')
            if not os.path.exists(path):
                sys.exit('Нет снимка %s' % path)
            shutil.copyfile(path, os.path.join(IMG, blob + '.jpg'))
    print('Стили %d Б, разметка %d Б, логика %d Б, снимков %d'
          % (len(css), len(markup), len(logic), len(blobs)))


if __name__ == '__main__':
    main()
