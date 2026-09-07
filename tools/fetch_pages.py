# -*- coding: utf-8 -*-
"""Догрузить перечисленные страницы документации.

Отдельно от `fetch_odoo_docs.py`: тот ходит по оглавлению, а здесь
список путей задан явно — то, что обход нашёл, а оглавление не отдало.
"""
import sys
sys.argv = [sys.argv[0]]          # чтобы main() чужого модуля не сработал
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from fetch_odoo_docs import BASE, fetch, to_markdown, save

def main(paths):
    saved = failed = 0
    for path in paths:
        html = fetch(BASE + path)
        if not html:
            print('  не открылась: %s' % path)
            failed += 1
            continue
        title, text = to_markdown(html, path)
        if not text:
            print('  пусто: %s' % path)
            failed += 1
            continue
        save(path, title, text)
        saved += 1
    print('saved: %s, failed: %s' % (saved, failed))

if __name__ == '__main__':
    main([line.strip() for line in open(sys.argv[1] if len(sys.argv) > 1 else 'pages.txt') if line.strip()])
