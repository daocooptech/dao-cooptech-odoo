# -*- coding: utf-8 -*-
"""Что из документации ещё не в базе.

Загрузчик брал ссылки только со страницы-оглавления. Оглавление у Odoo
полное, но не обязательно исчерпывающее: часть страниц видна лишь из
вложенных разделов. Обход по ссылкам показывает разницу точно, а не
на глаз.
"""
import os
import re
import sys
import requests

BASE = 'https://www.odoo.com/documentation/19.0/'
VAULT = os.path.join(os.environ['USERPROFILE'], 'Documents', 'Obsidian',
                     'Vault', 'Матчасть', 'Odoo 19')
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; DAO KOOPTEH docs mirror)'})

def links_of(html, prefixes, page):
    base_dir = page.rsplit('/', 1)[0] if '/' in page else ''
    found = set()
    for match in re.finditer(r'href="([^"#]+\.html)(?:#[^"]*)?"', html):
        href = match.group(1)
        if href.startswith(('http', '//', 'mailto')):
            continue
        # Относительные ссылки считаются от папки страницы, иначе
        # вложенные разделы теряются целиком.
        if href.startswith('../') or not href.startswith('/'):
            parts = (base_dir.split('/') if base_dir else []) + href.split('/')
            stack = []
            for part in parts:
                if part == '..':
                    if stack:
                        stack.pop()
                elif part not in ('.', ''):
                    stack.append(part)
            href = '/'.join(stack)
        href = href.lstrip('/')
        if href.split('/')[0].replace('.html', '') in prefixes:
            found.add(href)
    return found

def crawl(roots, prefixes):
    seen, queue, all_pages = set(), list(roots), set()
    while queue:
        page = queue.pop()
        if page in seen:
            continue
        seen.add(page)
        try:
            response = SESSION.get(BASE + page, timeout=60)
        except requests.RequestException:
            continue
        if response.status_code != 200:
            continue
        all_pages.add(page)
        for link in links_of(response.text, prefixes, page):
            if link not in seen:
                queue.append(link)
    return all_pages

if __name__ == '__main__':
    roots = sys.argv[1].split(',')
    prefixes = tuple(sys.argv[2].split(','))
    pages = crawl(roots, prefixes)
    missing = [p for p in sorted(pages)
               if not os.path.exists(os.path.join(VAULT, p.replace('.html', '') + '.md'))]
    print('всего страниц по обходу: %s' % len(pages))
    print('нет в базе: %s' % len(missing))
    for p in missing:
        print('  ' + p)
