# -*- coding: utf-8 -*-
"""Штатные дашборды Odoo по-русски (решение 707, задача 494).

Тексты ячеек дашбордов Odoo переводит сам (`_t` и ru.po модулей), а имена
мер сводных таблиц (`userDefinedName`, вычисляемые меры) и названия сводных
и списков — нет: они уходят в шапки таблиц и подсказки как есть, по-английски
(«Amount», «Ratio», «Revenue»). Подменяем их при выдаче дашборда — файлы
движка не трогаем, ключи мер в формулах не меняются.
"""
import json

from odoo import models

# Имена мер — то, что видно в шапках таблиц.
MEASURES = {
    'Amount': 'Сумма',
    'Ratio': 'Доля',
    'Revenue': 'Выручка',
    'Units': 'Штук',
    'Orders': 'Заказов',
    'Events': 'Мероприятий',
    'Tickets': 'Билетов',
    'Tasks': 'Задач',
    'Hours Logged': 'Часов учтено',
    'Hours Logged 2': 'Часов учтено',
    'Days': 'Дней',
    'Days Spent': 'Дней затрачено',
    'Billable Days': 'Оплачиваемых дней',
    'NonBillable Days': 'Неоплачиваемых дней',
    'Quantity': 'Количество',
    'Quantity Sold': 'Продано, шт.',
    'Total': 'Итого',
    '# Expenses': 'Расходов',
}

# Названия сводных и списков — видны в подсказках и при раскрытии таблицы.
SOURCES = {
    'Top Categories': 'Лучшие категории',
    'Country': 'Страна',
    'Product': 'Товар',
    'Products': 'Товары',
    'Product (copy)': 'Товар',
    'Salesperson': 'Продавец',
    'Category': 'Категория',
    'Customer': 'Покупатель',
    'Sales Team': 'Команда продаж',
    'Source': 'Источник',
    'Medium': 'Канал',
    'Tag': 'Метка',
    'Organizer': 'Организатор',
    'Top Venues': 'Лучшие площадки',
    'Event by Template': 'Мероприятия по шаблону',
    'Assignee': 'Исполнитель',
    'Project': 'Проект',
    'Project (copy)': 'Проект',
    'Tasks Analysis by Customer': 'Задачи по заказчикам',
    'KPI - Income': 'Доход',
    'KPI - Average Invoice': 'Средний счёт',
    'KPI - Unpaid Invoices': 'Неоплаченные счета',
    'Invoices by Total Signed': 'Счета по сумме',
    'Sales Analysis': 'Анализ продаж',
    'Sales Analysis by Qty Ordered': 'Продажи по количеству',
    'Timesheets Analysis by Project': 'Табели по проектам',
    'Timesheets Analysis by Task': 'Табели по задачам',
    'Timesheets Analysis by Department': 'Табели по отделам',
    'Timesheets Analysis by Employee': 'Табели по сотрудникам',
    'Timesheets Analysis by Non-billable Project': 'Неоплачиваемые часы по проектам',
    'Timesheets Analysis by Non-billable Task': 'Неоплачиваемые часы по задачам',
    'Timesheet Encoding Unit': 'Единица учёта времени',
    'Inventory - locations': 'Запасы по местам хранения',
    'Inventory - products sort by Qty': 'Запасы по количеству',
    'Inventory - locations (reserved stock)': 'Резерв по местам хранения',
    'Inventory by Product sort by value': 'Запасы по стоимости',
    'Inventory by Location sort by value': 'Места хранения по стоимости',
    'Inventory by Location sort by value (reserved stock)': 'Резерв по стоимости',
}


# Английские строки внутри формул ячеек («8 out of 7 943», «No data»).
FORMULA_TEXT = {
    '" out of "': '" из "',
    '"No data"': '"нет данных"',
    '" days"': '" дн."',
    '"Hours spent"': '"Затрачено часов"',
    '"Days spent"': '"Затрачено дней"',
    '"Billable rate"': '"Доля оплачиваемого"',
    '"Hours billed"': '"Часов к оплате"',
    '"Days billed"': '"Дней к оплате"',
    '"Hours logged"': '"Часов учтено"',
    '"Total quotations"': '"Всего предложений"',
    '"Total orders"': '"Всего заказов"',
    '"Total inventory value"': '"Стоимость запасов"',
    '"Quotations sent"': '"Отправлено предложений"',
    '"Draft quotations"': '"Черновики предложений"',
    '"Grand total"': '"Итого"',
}


def _ru_cells(snapshot):
    for sheet in snapshot.get('sheets') or []:
        cells = sheet.get('cells') or {}
        for key, cell in cells.items():
            text = cell.get('content') if isinstance(cell, dict) else cell
            if not isinstance(text, str) or not text.startswith('='):
                continue
            new = text
            for en, ru in FORMULA_TEXT.items():
                new = new.replace(en, ru)
            if new != text:
                if isinstance(cell, dict):
                    cell['content'] = new
                else:
                    cells[key] = new


def _fix_engine(snapshot):
    # «Продажи»: в файле движка плитка «Выручка» ссылается на ячейку, где
    # вместо формулы осталось число «-234», — считаем как соседние плитки.
    for sheet in snapshot.get('sheets') or []:
        cells = sheet.get('cells') or {}
        if sheet.get('name') == 'Data' and cells.get('D7') == '-234':
            cells['D7'] = '=FORMAT.LARGE.NUMBER(B7)'


# Заголовки плиток, которых нет в переводе движка.
FIGURE_TITLES = {
    'DSO': 'Срок оплаты, дн.',
}


def _ru_figures(snapshot):
    for sheet in snapshot.get('sheets') or []:
        for figure in sheet.get('figures') or []:
            title = (figure.get('data') or {}).get('title')
            if isinstance(title, dict) and title.get('text') in FIGURE_TITLES:
                title['text'] = FIGURE_TITLES[title['text']]


def _ru_snapshot(snapshot):
    _ru_cells(snapshot)
    _ru_figures(snapshot)
    for pivot in (snapshot.get('pivots') or {}).values():
        if pivot.get('name') in SOURCES:
            pivot['name'] = SOURCES[pivot['name']]
        for measure in pivot.get('measures') or []:
            # Вычисляемая мера без своего имени показывает ключ — даём имя,
            # ключ (`fieldName`, `id`) остаётся: на него ссылаются формулы.
            shown = measure.get('userDefinedName') or (
                measure.get('computedBy') and measure.get('fieldName'))
            if shown in MEASURES:
                measure['userDefinedName'] = MEASURES[shown]
    for lst in (snapshot.get('lists') or {}).values():
        if lst.get('name') in SOURCES:
            lst['name'] = SOURCES[lst['name']]
    return snapshot


class SpreadsheetDashboard(models.Model):
    _inherit = 'spreadsheet.dashboard'

    def _get_serialized_readonly_dashboard(self):
        data = super()._get_serialized_readonly_dashboard()
        payload = json.loads(data)
        snapshot = payload.get('snapshot') or {}
        _fix_engine(snapshot)
        if (self.env.lang or '').startswith('ru'):
            _ru_snapshot(snapshot)
        # Денежные форматы движка зашиты долларом («[$$]#,##0») — ставим
        # валюту компании после числа, как пишут суммы по-русски.
        symbol = (payload.get('default_currency') or {}).get('symbol') or '₽'
        formats = snapshot.get('formats') or {}
        for key, fmt in formats.items():
            if isinstance(fmt, str) and '[$$]' in fmt:
                formats[key] = fmt.replace('[$$]', '').replace('[$]', '') + '[$ %s]' % symbol
        return json.dumps(payload)
