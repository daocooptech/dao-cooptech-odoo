# Чужие модули, которые мы портировали

Здесь лежат не наши модули, а форки — с правками, без которых они не
работают на Odoo 19. Хранятся у нас по одной причине: **правка чужого
модуля на месте живёт до первого обновления дистрибутива**, и её надо
держать там, где её видно.

Правильный конец истории — отдать правки наверх: в OCA для `l10n_ru`, в
консорциум Rudoo для его модулей. Пока этого не произошло, папка остаётся.

## l10n_ru — план счетов по приказу Минфина 94н

Источник: [OCA/l10n-russia](https://github.com/OCA/l10n-russia), ветка 17.0,
лицензия AGPL-3. Ветка 19.0 в репозитории есть, но пустая: модули туда ещё
не мигрировали.

Исходники лежат рядом со стендом — `rudoo/oca-l10n-russia`, отдельная
рабочая копия. Она **не в `addons_path`** и туда не добавляется: движок
взял бы непортированный модуль вместо нашего форка, причём молча — по
порядку каталогов. Копия нужна ровно для одного: посмотреть `diff` и
понять, что именно мы изменили.

Что пришлось поправить:

- **Серия в манифесте.** Odoo 19 проверяет её сам и ставит
  `installable = False`, если серия чужая: модуль просто не появляется в
  списке. Поднято до 19.0.
- **Журналы кассы и банка.** Шаблон объявлял только счёт по умолчанию, без
  имени, типа и кода. В Odoo 19 код журнала обязателен, и создание падало
  на ограничении not null. Добавлены имя, тип и код.

Результат: 343 счёта российского плана.

## l10n_ru_banks — справочник банков

Тот же источник. Поправлено: ссылка на меню `account.account_banks_menu`,
которого в Odoo 19 больше нет, и поле `numbercall` у `ir.cron`, удалённое
из модели.

Работает и стоит и на стенде, и на боевой: 1399 банков. Прежняя запись
здесь говорила, что модуль в сборку не включён, — это устарело.

## l10n_ru_advance_payments — авансовые счета (Rudoo, MK.Lab)

Источник: [ruodoo-public](https://git.ruodoo.ru/ruodoo-public/public.git),
у нас — `rudoo/rudoo-addons/l10n_ru_advance_payments`. Стоит на боевой.

Что пришлось поправить (28.09.2026, решение 433, п. 19):

- **Поиск счёта расчётов по умолчанию** (`models/account_payment.py`,
  `_get_partner_account`) фильтровал по полю `deprecated`, которого у
  `account.account` в Odoo 19 нет — его заменил `active`. Платёж партнёру
  без своего счёта расчётов падал с «Invalid field
  account.account.deprecated». Условие убрано: архивные счета поиск и так не
  возвращает. Воспроизведено на копии боевой до правки и проверено после.

Остальные файлы — байт в байт с источником (`diff -r` показывает одну строку).

# Линия 20: цепочка российских модулей и расширения (этап Э5, 06.10.2026)

Ветка `20.0-ru`. Решение 445: цепочка учёта и документов и три расширения
переносятся на Odoo 20. Исходник у всех — `rudoo/rudoo-addons` (версия под
Odoo 19, репозиторий Rudoo `ruodoo-public`; OCA-модули в нём — копии 19.0).
Лицензии и авторство в манифестах сохранены как есть: где у источника нет
ключа `license`, его нет и здесь (Odoo 20 в этом случае считает LGPL-3 и
пишет предупреждение при загрузке — это не ошибка).

Порядок работы по каждому модулю: копия как есть отдельным коммитом, затем
штатный `odoo-bin upgrade_code` (по одному скрипту на коммит), затем ручная
правка. `git log --oneline -- forks/<модуль>` показывает всё, что менялось.

## Что взято и откуда

| Модуль | Источник | Лицензия | Что сделано для 20 |
|---|---|---|---|
| `l10n_ru_base` | Rudoo, MK.Lab | LGPL-3 | `_()` на уровне класса убран, версия 20.0 |
| `l10n_ru_doc` | Rudoo, CodeUP и MK.Lab | AGPL-3 | `t-esc`/`t-raw` → `t-out` (211), `helper.img` возвращает `Markup`, `pycompat` убран, `line.name` → `line.label`, поле `company_registry`, `uom`, `report_file`, отдельный compute `price_total_pf`, `ir.access` не потребовался |
| `l10n_ru_contract` | Rudoo, MK.Lab | ключа нет | `t-esc`/`t-raw` → `t-out` (246), `datas` → `raw`, base64 → строка, `pycompat` убран, `pymorphy2` → `pymorphy3`, `ir.access` |
| `l10n_ru_act_rev` | Rudoo, MK.Lab | ключа нет | `t-out`, `read_group` → `formatted_read_group` (помощник `_read_group_dicts`), `account.account.group_id` убран, `ir.access` |
| `l10n_ru_upd_xml` | Rudoo, MK.Lab | ключа нет | `t-out`, импорты контроллера, место группы XML-отчёта в форме отчёта, `hs_code` через `get_hs_code()`, `name` черновика, `line.label`; осиротевший `ir.model.access.csv` убран |
| `docx_report_generation` | Rudoo, RYDLAB | LGPL-3 | `get_param` → `get_str`, `request.website` → `env.website`, `BinaryValue.content` вместо `b64decode`, импорты контроллера |
| `custom_report_field` | Rudoo, RYDLAB | LGPL-3 | `ir.access` |
| `report_monetary_helpers` | Rudoo, RYDLAB | LGPL-3 | только версия |
| `report_weasyprint` | Rudoo, MK.Lab | LGPL-3 | `get_param` → `get_str`. **Не портирован по существу**: подмена `_run_wkhtmltopdf` в 20 мертва, см. ниже |
| `l10n_ru` | OCA, наш форк 19 | AGPL-3 | пустой `account.group-ru.csv` убран, данные компании в шаблоне плана счетов (`receivable/payable/expense/income_account_id`, storno, сумма прописью) |
| `l10n_ru_banks` | OCA, наш форк 19 | AGPL-3 | `ir.access`; **провизорно** воссоздана модель `res.bank` (см. ниже) |
| `l10n_ru_advance_payments` | Rudoo, MK.Lab, наш форк 19 | ключа нет | `t-out`, `pycompat`, `acc_number` → `account_number`, `selection` у related-поля |
| `base_tier_validation` | OCA `server-ux` 19.0 | AGPL-3 | `ir.access` (правила записей внутри), `static props` убран, `auto_join` убран |
| `base_user_role` | OCA `server-backend` 19.0 | LGPL-3 | `ir.rule` и `ir.model.access` слиты в `ir.access`: у роли один список доступов; `_sql_constraints` → `models.Constraint` |
| `dadata_connector` | Rudoo, MK.lab | ключа нет | `get_param` → `get_str`, `static props` → `useProps` |

Версии в манифестах подняты с 19.0.* до 20.0.*; серия 19 для Odoo 20 даёт
`installable = False`. Не переносились: `translation_helper`, `dms` и прочие
модули Rudoo (решение 445).

## Что в Odoo 20 изменилось и задевает эти модули

- **`t-esc`, `t-raw` удалены**, остался `t-out`. HTML, который раньше шёл через
  `t-raw`, должен быть `Markup`: так сделаны `img()` печатей и факсимиле,
  поля `Html` отдают `Markup` сами.
- **Название позиции.** `account.move.line.name` и `sale.order.line.name` теперь
  только описание, название — в поле `label` (`product.display_name` + описание).
  Печатные формы и УПД читают `label`.
- **`res.bank` удалена.** Реквизиты банка лежат в `res.partner.bank`
  (`bank_name`, `bank_bic`, адрес, `clearing_label_id`, `clearing_number`),
  номер счёта называется `account_number` (было `acc_number`).
- **`res.company.company_registry` удалено** (есть `additional_identifiers`,
  ключа ОГРН для RU нет): поле заведено в `l10n_ru_doc`.
- **Движки печати вынесены в модули** (`base_report_wkhtmltox`,
  `base_report_paper_muncher`): `_run_wkhtmltopdf(self, args)` теперь принимает
  аргументы командной строки, а выбор движка идёт через
  `_run_pdf_engine(engine_name, html, report_ref, landscape, **kwargs)`.
- `ir.actions.report.report_file` удалено; `account.account.group_id` и
  `account.group` удалены; `account.move.name` черновика — `False`;
  `read_group` отдаёт кортежи (словари — `formatted_read_group` из `web`);
  `hs_code` продукта — в `stock_delivery`; `odoo.tools.pycompat` нет;
  `_context` у записи устарел (`env.context`).

## Зависимости Python (venv `rudoo20`, Python 3.12, PyPI)

`weasyprint==70.0` (тянет `pydyf 0.12.1`, `pyphen 0.18.1`, `tinycss2 1.5.1`,
`tinyhtml5 2.1.0`, `cssselect2 0.10.1`, `fonttools 4.66.1`, `brotli 1.2.0`,
`zopfli 0.4.3`, `webencodings 0.6.1`), `docxtpl==0.20.2`, `docxcompose==2.2.0`,
`python-docx==1.2.0`, `beautifulsoup4==4.15.0` (в манифесте имя PyPI, а не `bs4`),
`pytils==0.4.4`, `num2words==0.5.13`, `dadata==21.10.1` (тянет `httpx 0.28.1`,
`httpcore 1.0.9`, `anyio 4.15.1`), `pymorphy3==2.0.6` и
`pymorphy3-dicts-ru==2.4.417150.4580142` вместо `pymorphy2` (тот не работает на
Python ≥ 3.11), для тестов OCA — `odoo-test-helper`. WeasyPrint на Windows
требует библиотеки Pango/GTK: на стенде их нет, `import weasyprint` падает, модуль
`report_weasyprint` это переживает (предупреждение), PDF через него не проверен.
На Linux-сервере нужны системные пакеты `libpango-1.0-0`, `libpangoft2-1.0-0`.

## Открытое (решает основная сессия)

См. отчёт этапа Э5: `report_weasyprint` (движок печати), справочник банков
(коммит «ПРОВИЗОРНО — res.bank воссоздан»), схема XML УПД (5.03), `company_registry`,
`fa-*` значки в OCA-модулях, семантика `base_user_role` (тесты), поломка
`payment` в форке движка (данные ссылаются на снятые модули).
