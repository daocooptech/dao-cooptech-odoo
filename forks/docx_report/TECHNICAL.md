# DOCX-шаблоны
name: docx_report
version: 19.0.1.0.0
author: MK.Lab
depends: `base`, `account`, `sale`, `l10n_ru_contract`, `docx_report_generation`
external_dependencies: `docxtpl`, `docxcompose`, `bs4`

## Архитектура

Модуль надстраивается над `docx_report_generation` и добавляет интерфейс управления шаблонами. Ключевая модель `docx.template` наследует технические поля в `ir.actions.report` через `_inherits`.

```
docx_report
├── docx.template          — шаблон (наследует ir.actions.report через _inherits)
├── docx.custom.field      — кастомные переменные шаблона
├── docx.template.mixin    — AbstractModel для привязки шаблона к модели
├── ir.actions.report      — расширение: рендер DOCX, кастомные переменные, валидация
├── ir.model               — расширение: display_name в контексте docx_template
├── ir.model.fields        — расширение: вычисляемый тип поля для подсказки
└── DocxReportController   — HTTP-контроллер: скачивание DOCX и PDF
```

---

## Модели

### `docx.template` — Шаблон

**Файл:** `models/docx_template.py`

Использует `_inherits = {"ir.actions.report": "report_id"}` — все технические поля (`name`, `model`, `report_type`, `report_docx_template`) берутся из связанного `ir.actions.report`.

| Поле | Тип | Описание |
|---|---|---|
| `report_id` | Many2one → `ir.actions.report` (required, cascade) | Связанное действие отчёта |
| `filename_pattern` | Char | Python-выражение для имени скачиваемого файла (без расширения). Переменные: `object`, `time` |
| `docx_output_type` | Selection (`docx`) | Формат вывода |
| `docx_model_id` | Many2one → `ir.model` | Модель документа (устанавливает `model` в `ir.actions.report`) |
| `available_field_ids` | Many2many → `ir.model.fields` (computed) | Доступные поля модели |
| `global_template` | Boolean (default: True) | Глобальный шаблон — доступен для всех записей модели |
| `hint_model_id` | Many2one → `ir.model` | Модель для подсказки полей |
| `report_docx_template_filename` | Char | Имя загруженного файла шаблона |

#### Методы

**`_compute_available_field_ids()`** — вычисляет список полей модели для вкладки «Доступные переменные». 

**`create()` / `write()`** — при сохранении синхронизируют `docx_output_type` → `report_type` (`docx` → `docx-docx`) и `docx_model_id` → `model` в связанном `ir.actions.report`.

**`action_bind_to_actions()`** — создаёт `binding` для отображения шаблона в меню.

**`action_unbind_from_actions()`** — удаляет привязку через `unlink_action()`.

**`action_bind_all_to_actions()`** — добавляет в меню печати все шаблоны сразу.

**`action_validate_docx_template()`** — валидирует загруженный шаблон:
1. Распаковывает `.docx` как ZIP, читает XML-файлы внутри `word/`
2. Извлекает все выражения `{{ }}` и переменные циклов `{% for %}`
3. Для каждого выражения разбирает цепочку полей и проверяет их существование через `self.env[model_name]._fields`
4. Возвращает уведомление: успех или список неизвестных переменных

---

### `docx.custom.field` — Кастомная переменная

**Файл:** `models/docx_custom_field.py`

| Поле | Тип | Описание |
|---|---|---|
| `report_id` | Many2one → `ir.actions.report` (required, cascade) | Основной отчёт |
| `technical_name` | Char (required) | Имя переменной в шаблоне |
| `name` | Char (required) | Отображаемое название |
| `value_python` | Text (required) | Python-выражение. Контекст: `env`, `user`, `record`, `docs`, `time`, `context` |

---

### `docx.template.mixin` — Миксин

**Файл:** `models/docx_template_mixin.py`

Добавляет поле `docx_template_id` (Many2one → `docx.template`) в любую модель. Используется для хранения шаблона по умолчанию для конкретного объекта (например, вид договора → шаблон).

---

### `ir.actions.report` — Расширение

**Файл:** `models/ir_actions_report.py`

Добавляет поля и реализует рендер DOCX.

| Поле | Тип | Описание |
|---|---|---|
| `docx_custom_field_ids` | One2many → `docx.custom.field` | Кастомные переменные |
| `report_docx_template` | Binary | Загруженный `.docx`-файл шаблона |
| `report_type` | Selection (расширение) | Добавлен тип `docx-docx` |
| `report_name` | Char (computed) | Формат: `{model}-docx_report+{id}` для DOCX-отчётов |

#### Метод `_render_docx_template(template, values)`

Основной метод рендеринга. Последовательность:

1. Формирует базовый контекст: `record`, `time`, `user`, `res_company`, `web_base_url`, `website`
2. Вычисляет кастомные переменные через `safe_eval` и добавляет их в контекст
3. Рендерит шаблон через `DocxTemplate` (библиотека `docxtpl`)
4. Возвращает `BytesIO` с готовым DOCX

#### Метод `_render_docx_docx(res_ids, data)`

Оркестрирует рендер для списка записей: поддерживает кэш вложений, рендерит по одной записи, объединяет через `_merge_docx()` если несколько.

#### Метод `_merge_docx(streams)`

Объединяет несколько DOCX-файлов в один через `docxcompose.Composer` с разрывами страниц между ними.

#### Метод `_parse_markup(markup_data)`

Конвертирует HTML-поля Odoo в plain text для вставки в DOCX через `BeautifulSoup`.

---

### `ir.model.fields` — Расширение

**Файл:** `models/ir_model_fields.py`

Добавляет вычисляемое поле `docx_type_label` — человекочитаемый тип поля для вкладки «Доступные переменные»:
- Many2one/One2many/Many2many: `many2one (res.partner)`
- Selection: `selection (value1, value2)`

---

## HTTP-контроллер

**Файл:** `controllers/main.py`  
**Класс:** `DocxReportController` (наследует `ReportController`)

### Маршрут `report_routes`

Расширяет стандартный маршрут `/report/<converter>/<reportname>/<docids>`:

| Converter | Действие |
|---|---|
| `docx` | Вызывает `_render_docx_docx()`, возвращает DOCX с MIME-типом `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| `pdf` (для DOCX-отчёта) | Вызывает `_render_docx_pdf()` (из `docx_report_generation`) |
| Остальные | Передаёт в родительский `ReportController` |

### Маршрут `report_download`

Обрабатывает скачивание файлов типов `docx-docx` и `docx-pdf`. Формирует имя файла через `_get_docx_output_filename()`:

| Приоритет | Источник имени |
|---|---|
| 1 | `docx.template.filename_pattern` (Python-выражение) |
| 2 | `ir.actions.report.print_report_name` |
| 3 | `ir.actions.report.name` |

---

## Представления и меню

**Файл:** `views/docx_template_views.xml`

Форма шаблона содержит:
- Кнопка **«Валидация»** в header
- Кнопки **«Добавить печать в действия»** / **«Убрать печать из действий»** в button_box
- Основные поля: название, формат, модель, файл шаблона, шаблон имени файла, флаг «Глобальный»
- Вкладка **«Кастомные переменные»** — список `docx_custom_field_ids`
- Вкладка **«Доступные переменные»** — readonly список полей модели с техническим именем, названием и типом

Пункт меню **«Шаблоны для отчетов»** добавляется в корень главного меню.

---

## Безопасность

**Файл:** `security/ir.model.access.csv`

CRUD-права на `docx.template` и `docx.custom.field` для стандартных групп пользователей.

---

## Тесты

**Файл:** `tests/test_docx.py`

Покрывает создание шаблона, валидацию, рендер DOCX для тестовой модели.
