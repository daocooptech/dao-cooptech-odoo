# -*- coding: utf-8 -*-
"""Загрузить документацию Odoo 19 в базу знаний.

Что берём: задаётся при запуске. Прикладные разделы, справочник
разработчика, администрирование — три отдельных прогона, потому что
оглавления у них разные:

    python fetch_odoo_docs.py applications.html
    python fetch_odoo_docs.py developer.html developer
    python fetch_odoo_docs.py administration.html administration

Как храним: одна страница — одна заметка, путь сайта повторяется папками
внутри `Матчасть/Odoo 19/`. Так по ссылке из документации всегда понятно,
где заметка лежит, и наоборот.

Что выкидываем: навигацию, оглавление сайдбара, футер, кнопки правки —
всё, что не текст страницы. Остаётся заголовок, текст, списки, таблицы и
блоки кода.
"""
import io
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup
import html2text

BASE = 'https://www.odoo.com/documentation/19.0/'
VAULT = os.path.join(os.environ['USERPROFILE'], 'Documents', 'Obsidian',
                     'Vault', 'Матчасть', 'Odoo 19')

# Прикладные разделы. Остальное (разработка, установка) — отдельной
# задачей, если понадобится.
WANTED_PREFIXES = (
    'applications', 'finance', 'inventory_and_mrp', 'sales', 'websites',
    'hr', 'marketing', 'services', 'productivity', 'essentials', 'general',
    'studio',
)

# Заголовки передаются в latin-1, кириллица в них не проходит вовсе —
# запрос падает ещё до отправки.
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; DAO KOOPTEH docs mirror '
                         'for internal knowledge base)'}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def fetch(url, attempts=3):
    """Скачать страницу, не падая на первой же ошибке сети.

    Соединение переиспользуется одной сессией: девять сотен страниц
    отдельными подключениями — это девять сотен рукопожатий TLS, вдвое
    дольше и вдвое заметнее для чужого сервера.
    """
    for attempt in range(attempts):
        try:
            response = SESSION.get(url, timeout=60)
            if response.status_code == 200:
                return response.text
            if response.status_code == 404:
                return None
        except requests.RequestException:
            pass
        if attempt < attempts - 1:
            time.sleep(2 * (attempt + 1))
    return None


def collect_links(html, prefixes):
    """Ссылки на страницы нужных разделов, без якорей и повторов."""
    links = set()
    for match in re.finditer(r'href="([^"#]+\.html)(?:#[^"]*)?"', html):
        href = match.group(1)
        if href.startswith(('http', '//', 'mailto')):
            continue
        href = href.lstrip('./')
        if href.split('/')[0].replace('.html', '') in prefixes:
            links.add(href)
    return sorted(links)


def to_markdown(html, url):
    """Оставить от страницы текст, выкинув обвязку сайта."""
    soup = BeautifulSoup(html, 'html.parser')
    main = (soup.find('div', {'role': 'main'}) or soup.find('main')
            or soup.find('article'))
    if main is None:
        return None, None

    for tag in main.select('.headerlink, .o_toc, nav, .admonition-title-icon,'
                           ' script, style, .edit-on-github, .doc-nav'):
        tag.decompose()

    heading = main.find(['h1', 'h2'])
    title = heading.get_text(strip=True) if heading else url

    converter = html2text.HTML2Text()
    converter.body_width = 0          # переносы ставит читатель, не файл
    converter.ignore_images = True    # картинки остаются на сайте
    converter.ignore_emphasis = False
    converter.mark_code = True
    text = converter.handle(str(main))
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return title, text


def save(path, title, text):
    target = os.path.join(VAULT, path.replace('.html', '') + '.md')
    os.makedirs(os.path.dirname(target), exist_ok=True)
    header = (
        '---\n'
        'type: reference\n'
        'source: odoo-docs-19\n'
        'url: ' + BASE + path + '\n'
        'tags:\n  - матчасть\n  - odoo\n'
        '---\n'
    )
    # Свой заголовок ставится, только если страница не начинается со
    # своего: иначе в заметке два одинаковых заголовка подряд.
    if text.lstrip().startswith('# '):
        body = text
    else:
        body = '# ' + title + '\n\n' + text
    io.open(target, 'w', encoding='utf-8', newline='\n').write(
        header + body + '\n')


def main():
    # Аргументы: страница-оглавление, список разделов через запятую,
    # предел числа страниц (ноль — без предела).
    entry = sys.argv[1] if len(sys.argv) > 1 else 'applications.html'
    prefixes = (tuple(sys.argv[2].split(',')) if len(sys.argv) > 2
                else WANTED_PREFIXES)
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    index = fetch(BASE + entry)
    if not index:
        print('оглавление не открылось')
        return
    links = collect_links(index, prefixes)
    if limit:
        links = links[:limit]
    print('страниц к загрузке: %s' % len(links))

    saved = failed = 0
    for number, path in enumerate(links, 1):
        html = fetch(BASE + path)
        if not html:
            failed += 1
            continue
        title, text = to_markdown(html, path)
        if not text:
            failed += 1
            continue
        save(path, title, text)
        saved += 1
        if number % 50 == 0:
            print('  %s из %s' % (number, len(links)))
        # Пауза, чтобы не выглядеть налётом на чужой сайт.
        time.sleep(0.25)

    print('сохранено: %s, не удалось: %s' % (saved, failed))


if __name__ == '__main__':
    main()
