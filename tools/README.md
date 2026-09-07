# Выгрузка документации Odoo 19 в базу знаний

Зачем: устройство движка приходится выяснять по ходу дела, и почти всегда
ответ есть в документации. Держать её рядом с проектом дешевле, чем
каждый раз ходить на сайт.

Куда кладётся: `%USERPROFILE%\Documents\Obsidian\Vault\Матчасть\Odoo 19\`,
одна страница — одна заметка, путь сайта повторён папками.

Питон нужен с `requests`, `bs4`, `html2text`. Системный их не имеет,
подходит окружение стенда: `rudoo/venv/Scripts/python.exe`.

```bash
PY="D:/dao cooptech/rudoo/venv/Scripts/python.exe"

# Три прогона — оглавления у разделов разные.
"$PY" fetch_odoo_docs.py applications.html
"$PY" fetch_odoo_docs.py developer.html developer
"$PY" fetch_odoo_docs.py administration.html administration

# Проверка полноты: обход по ссылкам находит страницы, которых нет в
# оглавлении. Печатает список недостающих.
"$PY" check_missing.py developer.html,administration.html developer,administration

# Догрузка перечисленного построчно в файле.
"$PY" fetch_pages.py pages.txt
```

Почему проверка отдельным сценарием: загрузчик берёт ссылки только со
страницы-оглавления, а часть страниц видна лишь из вложенных разделов.
На сентябрь 2026 так недосчитались 13 страниц справочника из 149.
