# -*- coding: utf-8 -*-
"""Сбор мирового каталога приложений Odoo (apps.odoo.com) для витрины
«Сторонние приложения» в каталоге расширений.

Владелец 12.10.2026: «мировой каталог https://apps.odoo.com/apps/modules
обозначить его как сторонние приложения»; сторонние — витрина и ссылка,
без «Подключить».

Обходит страницы списка `/apps/modules/browse/page/N?series=S` — их
`robots.txt` не запрещает (запрещены `*/page/*/*` и сортировки). Темп —
один запрос в секунду; уже собранные страницы пропускает, так что
прерванный сбор продолжается с места.

    python fetch_odoo_apps.py <выходной.jsonl> [--series 19.0] [--delay 1.0]

Строка вывода — одна карточка: технический модуль, серия, название,
краткое описание, автор, цена, голоса, скачивания (у платных — покупки), картинка, адрес.
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE = 'https://apps.odoo.com'
UA = 'Mozilla/5.0 (compatible; daocooptech-catalog/1.0; +https://daocoop.tech)'

CARD = re.compile(r'<div class="loempia_app_entry loempia_app_card[^"]*"[^>]*>(.*?)</span>\s*</span>\s*</div>',
                  re.S)
HREF = re.compile(r'href="/apps/modules/([0-9.]+)/([A-Za-z0-9_]+)/?"')
SUMMARY = re.compile(r'<p class="loempia_panel_summary">(.*?)</p>', re.S)
TITLE = re.compile(r'<h5 title="([^"]*)"')
AUTHOR = re.compile(r'loempia_panel_author">\s*<b>(.*?)</b>', re.S)
PRICE = re.compile(r'loempia_panel_price[^>]*>(.*?)</div>', re.S)
VOTES = re.compile(r'title="(\d+) votes"')
# Платные показывают покупки, бесплатные — скачивания; это один счётчик
# «сколько раз взяли», и ранжировать по нему нужно оба вида.
TAKEN = re.compile(r'Total (Purchases|Downloads): (\d+)(?:, Last month: (\d+))?')
IMAGE = re.compile(r'module_image\?image_id=(\d+)')
LAST_PAGE = re.compile(r'/apps/modules/browse/page/(\d+)\?')


def text(fragment):
    return html.unescape(re.sub(r'<[^>]+>', ' ', fragment or '')).split() and \
        ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', fragment)).split()) or ''


def get(url, tries=4):
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode('utf-8', 'replace')
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            wait = 5 * (attempt + 1)
            print(f'  ! {url}: {error}; повтор через {wait} с', file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f'не получилось: {url}')


def parse(page_html, page):
    cards = []
    for block in CARD.findall(page_html):
        href = HREF.search(block)
        if not href:
            continue
        price = PRICE.search(block)
        price_text = text(price.group(1)) if price else ''
        amount = re.search(r'([0-9][0-9.,]*)', price_text)
        votes = VOTES.search(block)
        taken = TAKEN.search(block)
        image = IMAGE.search(block)
        cards.append({
            'module': href.group(2),
            'series': href.group(1),
            'name': html.unescape(TITLE.search(block).group(1)) if TITLE.search(block) else href.group(2),
            'summary': text(SUMMARY.search(block).group(1)) if SUMMARY.search(block) else '',
            'author': text(AUTHOR.search(block).group(1)) if AUTHOR.search(block) else '',
            'price': float(amount.group(1).replace(',', '')) if amount else 0.0,
            'price_text': price_text or 'Free',
            'votes': int(votes.group(1)) if votes else 0,
            'downloads': int(taken.group(2)) if taken else 0,
            'downloads_month': int(taken.group(3)) if taken and taken.group(3) else 0,
            'is_paid': bool(taken and taken.group(1) == 'Purchases'),
            'image_id': image.group(1) if image else '',
            'url': f'{BASE}/apps/modules/{href.group(1)}/{href.group(2)}',
            'page': page,
        })
    return cards


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('out')
    parser.add_argument('--series', default='19.0')
    parser.add_argument('--delay', type=float, default=1.0)
    parser.add_argument('--top', type=int, default=0,
                        help='после сбора записать N самых скачиваемых в <out>.topN.jsonl')
    args = parser.parse_args()

    done = set()
    if os.path.exists(args.out):
        with open(args.out, encoding='utf-8') as handle:
            for line in handle:
                try:
                    done.add(json.loads(line)['page'])
                except (ValueError, KeyError):
                    pass

    first = get(f'{BASE}/apps/modules/browse?series={args.series}')
    last = max([int(n) for n in LAST_PAGE.findall(first)] or [1])
    print(f'серия {args.series}: страниц {last}, уже собрано {len(done)}', flush=True)

    total = 0
    with open(args.out, 'a', encoding='utf-8') as out:
        for page in range(1, last + 1):
            if page in done:
                continue
            page_html = first if page == 1 else get(
                f'{BASE}/apps/modules/browse/page/{page}?series={args.series}')
            cards = parse(page_html, page)
            if not cards:
                # Пустая страница среди полных — признак, что разбор сломался,
                # а не что каталог кончился: молча идти дальше значит собрать
                # пустой файл и не заметить.
                print(f'  ! страница {page}: карточек 0', file=sys.stderr, flush=True)
            for card in cards:
                out.write(json.dumps(card, ensure_ascii=False) + '\n')
            out.flush()
            total += len(cards)
            if page % 50 == 0:
                print(f'страница {page}/{last}, карточек за проход {total}', flush=True)
            time.sleep(args.delay)
    print(f'готово: карточек за проход {total}', flush=True)

    if args.top:
        # Сортировки списка на сайте `robots.txt` запрещает (`?order=`), так
        # что «самые скачиваемые» отбираются здесь, по полному списку.
        best = {}
        with open(args.out, encoding='utf-8') as handle:
            for line in handle:
                card = json.loads(line)
                if card['module'] not in best or card['downloads'] > best[card['module']]['downloads']:
                    best[card['module']] = card
        top = sorted(best.values(), key=lambda c: c['downloads'], reverse=True)[:args.top]
        path = f'{os.path.splitext(args.out)[0]}.top{args.top}.jsonl'
        with open(path, 'w', encoding='utf-8') as handle:
            for card in top:
                handle.write(json.dumps(card, ensure_ascii=False) + '\n')
        print(f'лучшие {len(top)}: {path}; у последнего скачиваний '
              f'{top[-1]["downloads"] if top else 0}', flush=True)


if __name__ == '__main__':
    main()
