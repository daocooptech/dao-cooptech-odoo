# -*- coding: utf-8 -*-
"""Сборщик готовых дашбордов «Аналитики» (решение 420, слой 2).

Дашборд движка (`spreadsheet_dashboard`) — это таблица o-spreadsheet в
JSON: первый лист — лицо дашборда (плитки, графики, таблицы «топ-10»),
второй — числа для плиток, третий — справочники для фильтров. Руками такой
файл не пишут: идентификаторы, смещения в пикселях и привязки фильтров к
полям должны сходиться между собой. Поэтому файлы собираются здесь, а в
модуле лежит только результат.

    python tools/build_dashboards.py        пересобрать coop_analytics/data/dashboards/*.json

Формат сверен со штатными дашбордами Odoo 19
(`odoo/addons/spreadsheet_dashboard_*/data/files/*.json`, версия 18.4.14) и
с `Матчасть/Odoo 19/applications/productivity/dashboards/`.
"""
import json
import os
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'coop_analytics', 'data', 'dashboards')
NS = uuid.UUID('6f1c4d2e-5b7a-4c3e-9a41-2d0c7e1b8f53')

VERSION = '18.4.14'
BRAND = '#146b64'
CARD_BG = '#EEF6F5'
GOOD, BAD = '#00A04A', '#DC6965'

# Столбцы лица: две половины по 440 пикселей и зазор между ними. Всего 900:
# тема держит основную колонку в 1214 пикселей, из них 200 — список
# дашбордов слева, и на обычном мониторе таблице остаётся 962.
COLS = [250, 110, 80, 20, 250, 110, 80]
WIDTH = sum(COLS)
HALF = COLS[0] + COLS[1] + COLS[2]
RIGHT_X = HALF + COLS[3]
ROW = 23
TITLE_ROW = 40

# Города платформы — согласованный список плюс те, что уже есть в данных
# (память сессий «platform-city-list»; Иркутск, Курск, Псков, Тула — из
# сделок и проектов боевой базы).
CITIES = sorted([
    'Алтайский край', 'Архангельск', 'Владивосток', 'Волгоград', 'Вологда', 'Воронеж',
    'Дербент', 'Екатеринбург', 'Иркутск', 'Ишим', 'Казань', 'Калининград', 'Кемерово',
    'Краснодар', 'Красноярск', 'Курск', 'Магнитогорск', 'Москва', 'Нижний Новгород',
    'Нижний Тагил', 'Новосибирск', 'Омск', 'Пермь', 'Псков', 'Ростов-на-Дону', 'Самара',
    'Санкт-Петербург', 'Сочи', 'Тобольск', 'Тула', 'Тюмень', 'Уфа', 'Хабаровск',
    'Челябинск', 'Ярославль',
])

MONEY = '#,##0[$ ₽]'
INT = '#,##0'
PCT = '0[$ %]'


def col_letter(i):
    return 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[i]


class Dashboard:
    def __init__(self, key, title, menu):
        self.key = key
        self.title = title
        self.menu = menu            # пункт меню, куда ведёт щелчок по графику
        self.filters = []
        self.pivots = {}
        self.data_cells = {}
        self.data_formats = {}
        self.cells = {}
        self.styles = {}
        self.borders = {}
        self.rows = {}
        self.figures = []
        self.menu_refs = {}
        self.row = 0                # следующая свободная строка лица
        self.data_row = 1

    # ── идентификаторы ────────────────────────────────────────────────
    def uid(self, name):
        return str(uuid.uuid5(NS, '%s:%s' % (self.key, name)))

    # ── фильтры ───────────────────────────────────────────────────────
    def date_filter(self, name, label='Период', default='last_12_months'):
        f = {'id': self.uid('filter:' + name), 'type': 'date', 'label': label}
        if default:
            f['defaultValue'] = default
        self.filters.append(f)
        return f['id']

    def selection_filter(self, name, label, model, field):
        f = {'id': self.uid('filter:' + name), 'type': 'selection', 'label': label,
             'resModel': model, 'selectionField': field}
        self.filters.append(f)
        return f['id']

    def relation_filter(self, name, label, model):
        f = {'id': self.uid('filter:' + name), 'type': 'relation', 'label': label,
             'modelName': model, 'defaultValueDisplayNames': []}
        self.filters.append(f)
        return f['id']

    def city_filter(self, name='city', label='Город'):
        # Текстовый фильтр со списком допустимых значений — выпадающий
        # список городов, а не поле для ввода наугад.
        f = {'id': self.uid('filter:' + name), 'type': 'text', 'label': label,
             'rangesOfAllowedValues': ['Lists!A1:A%d' % len(CITIES)]}
        self.filters.append(f)
        return f['id']

    # ── источники ─────────────────────────────────────────────────────
    def pivot(self, name, model, domain, measures, matching, rows=None, sorted_by=None):
        pid = str(len(self.pivots) + 1)
        ms = []
        for m in measures:
            field, _, agg = m.partition(':')
            item = {'id': m, 'fieldName': field}
            if agg:
                item['aggregator'] = agg
            ms.append(item)
        self.pivots[pid] = {
            'type': 'ODOO', 'id': pid, 'formulaId': pid, 'name': name, 'model': model,
            'domain': domain, 'context': {}, 'measures': ms,
            'columns': [],
            'rows': [r if isinstance(r, dict) else {'fieldName': r} for r in (rows or [])],
            'sortedColumn': ({'measure': sorted_by, 'order': 'desc', 'domain': []}
                             if sorted_by else None),
            'fieldMatching': matching,
        }
        return pid

    def value(self, label, formula, fmt, previous=None):
        """Строка на листе Data: подпись, текущее значение, прошлый период."""
        r = self.data_row = self.data_row + 1
        self.data_cells['A%d' % r] = label
        self.data_cells['B%d' % r] = formula
        if fmt:
            self.data_formats['B%d' % r] = fmt
        if previous:
            # Ноль в прошлом периоде — сравнивать не с чем: пустая база, а
            # не «↑∞%» на плитке.
            prev = previous.lstrip('=')
            self.data_cells['C%d' % r] = '=IFERROR(IF((%s)=0,"",(%s)),"")' % (prev, prev)
            if fmt:
                self.data_formats['C%d' % r] = fmt
        return 'Data!B%d' % r, ('Data!C%d' % r if previous else None)

    # ── лицо ──────────────────────────────────────────────────────────
    def cards(self, items):
        """Плитки, не больше трёх в ряд. items: (заголовок, ключ, база, режим, рост_плох).

        Шесть в ряд при ширине 900 — это 141 пиксель на плитку, и сумма
        «462 616 ₽» обрезалась до «462 6…» (найдено глазами на копии).
        """
        per_row, gap, h = 3, 10, 96
        w = (WIDTH - gap * (per_row - 1)) // per_row
        for i, item in enumerate(items):
            title, key, base, mode, up_is_bad = (list(item) + [None, None, False])[:5]
            fid = self.uid('card:' + title)
            if mode == 'gauge':
                data = {
                    'type': 'gauge', 'background': CARD_BG, 'dataRange': key,
                    'title': {'text': title, 'bold': True, 'color': '#434343', 'fontSize': 14},
                    'sectionRule': {
                        'colors': {'lowerColor': '#cc0000', 'middleColor': '#f1c232',
                                   'upperColor': '#6aa84f'},
                        'rangeMin': '0', 'rangeMax': '100',
                        'lowerInflectionPoint': {'type': 'number', 'value': '40', 'operator': '<='},
                        'upperInflectionPoint': {'type': 'number', 'value': '70', 'operator': '<='},
                    },
                }
            else:
                data = {
                    'type': 'scorecard', 'background': CARD_BG, 'keyValue': key,
                    'title': {'text': title, 'bold': True, 'color': '#434343'},
                    'baselineColorUp': BAD if up_is_bad else GOOD,
                    'baselineColorDown': GOOD if up_is_bad else BAD,
                    'baselineMode': mode or 'difference', 'humanize': False,
                }
                if base:
                    data['baseline'] = base
                    if mode != 'text':
                        data['baselineDescr'] = {'text': 'к прошлому'}
            row, pos = divmod(i, per_row)
            self.figures.append({'id': fid, 'tag': 'chart', 'col': 0, 'row': 0,
                                 'offset': {'x': pos * (w + gap), 'y': 12 + row * (h + gap)},
                                 'width': w, 'height': h, 'data': data})
            self.menu_refs[fid] = self.menu
        rows = -(-len(items) // per_row)
        self.row = -(-(12 + rows * (h + gap)) // ROW)

    def _y(self, row):
        return sum(self.rows.get(str(r), {}).get('size', ROW) for r in range(row))

    def _title(self, col, text, span):
        r = self.row
        cell = '%s%d' % (col_letter(col), r + 1)
        self.cells[cell] = text
        self.styles[cell] = 1
        last = col_letter(col + span - 1)
        self.borders['%s:%s%d' % (cell, last, r + 1)] = 1

    def section(self, left, right=None, rows=15):
        """Заголовок и график во всю ширину или два графика рядом."""
        self.rows[str(self.row)] = {'size': TITLE_ROW}
        top = self._y(self.row + 1)
        halves = [(0, 0, left)] + ([(4, RIGHT_X, right)] if right else [])
        for col, x, (title, chart) in halves:
            self._title(col, title, 3 if right else len(COLS))
            fid = self.uid('chart:' + title)
            self.figures.append({'id': fid, 'tag': 'chart', 'col': 0, 'row': 0,
                                 'offset': {'x': x, 'y': top},
                                 'width': HALF if right else WIDTH, 'height': rows * ROW,
                                 'data': chart})
            self.menu_refs[fid] = self.menu
        self.row += 1 + rows + 1

    def tables(self, left, right=None, size=10):
        """Таблицы «топ-N» из сводных: =PIVOT(id, N) раскладывается сама."""
        self.rows[str(self.row)] = {'size': TITLE_ROW}
        for col, (title, pid) in [(0, left)] + ([(4, right)] if right else []):
            self._title(col, title, 3)
            self.cells['%s%d' % (col_letter(col), self.row + 2)] = \
                '=PIVOT(%s, %d, FALSE, FALSE)' % (pid, size)
        self.row += 1 + size + 2

    # ── сборка ────────────────────────────────────────────────────────
    def build(self):
        styles = {'1': {'textColor': BRAND, 'bold': True, 'fontSize': 16},
                  '2': {'bold': True}}
        data_cells = dict(self.data_cells)
        data_cells.update({'B1': 'Сейчас', 'C1': 'Прошлый период'})
        formats, fmt_ids = {}, {}
        data_formats = {}
        for cell, fmt in self.data_formats.items():
            if fmt not in fmt_ids:
                fmt_ids[fmt] = str(len(fmt_ids) + 1)
                formats[fmt_ids[fmt]] = fmt
            data_formats[cell] = int(fmt_ids[fmt])
        return {
            'version': VERSION,
            'sheets': [
                {'id': 'sheet1', 'name': 'Dashboard', 'colNumber': len(COLS),
                 'rowNumber': max(self.row + 2, 50),
                 'rows': self.rows,
                 'cols': {str(i): {'size': s} for i, s in enumerate(COLS)},
                 'merges': [], 'cells': self.cells, 'styles': self.styles,
                 'formats': {}, 'borders': self.borders,
                 'conditionalFormats': [], 'dataValidationRules': [], 'tables': [],
                 'figures': self.figures, 'areGridLinesVisible': False, 'isVisible': True,
                 'headerGroups': {'ROW': [], 'COL': []}, 'comments': {}},
                {'id': self.uid('sheet:data'), 'name': 'Data', 'colNumber': 3,
                 'rowNumber': max(self.data_row + 5, 20), 'rows': {},
                 'cols': {'0': {'size': 220}, '1': {'size': 140}, '2': {'size': 140}},
                 'merges': [], 'cells': data_cells,
                 'styles': {'A1': 2, 'B1': 2, 'C1': 2}, 'formats': data_formats, 'borders': {},
                 'conditionalFormats': [], 'dataValidationRules': [], 'tables': [],
                 'figures': [], 'areGridLinesVisible': True, 'isVisible': True,
                 'headerGroups': {'ROW': [], 'COL': []}, 'comments': {}},
                {'id': self.uid('sheet:lists'), 'name': 'Lists', 'colNumber': 1,
                 'rowNumber': len(CITIES) + 5, 'rows': {}, 'cols': {'0': {'size': 200}},
                 'merges': [],
                 'cells': {'A%d' % (i + 1): c for i, c in enumerate(CITIES)},
                 'styles': {}, 'formats': {}, 'borders': {},
                 'conditionalFormats': [], 'dataValidationRules': [], 'tables': [],
                 'figures': [], 'areGridLinesVisible': True, 'isVisible': True,
                 'headerGroups': {'ROW': [], 'COL': []}, 'comments': {}},
            ],
            'styles': styles,
            'formats': formats,
            'borders': {'1': {'bottom': {'style': 'thin', 'color': '#CCCCCC'}}},
            'revisionId': 'START_REVISION',
            'uniqueFigureIds': True,
            'settings': {'locale': {'name': 'Russian', 'code': 'ru_RU',
                                    'thousandsSeparator': ' ', 'decimalSeparator': ',',
                                    'dateFormat': 'dd.mm.yyyy', 'timeFormat': 'hh:mm:ss',
                                    'formulaArgSeparator': ';', 'weekStart': 1}},
            'pivots': self.pivots,
            'pivotNextId': len(self.pivots) + 1,
            'customTableStyles': {},
            'globalFilters': self.filters,
            'lists': {},
            'listNextId': 1,
            'chartOdooMenusReferences': self.menu_refs,
        }


def chart(kind, model, domain, group_by, measure, matching, legend='none', stacked=True,
          order=None, **extra):
    """График движка по модели: odoo_bar, odoo_line, odoo_pie."""
    mode = kind.split('_', 1)[1]
    meta = {'groupBy': group_by, 'measure': measure, 'order': order, 'resModel': model,
            'mode': mode, 'cumulatedStart': bool(extra.get('cumulatedStart'))}
    data = {'type': kind, 'title': {'text': ''}, 'background': '#FFFFFF',
            'legendPosition': legend, 'metaData': meta,
            'searchParams': {'comparison': None, 'context': {}, 'domain': domain,
                             'groupBy': group_by, 'orderBy': []},
            'dataSets': [], 'fieldMatching': matching}
    if kind != 'odoo_pie':
        data.update({'verticalAxisPosition': 'left', 'stacked': stacked})
    if kind == 'odoo_line':
        data.update({'fillArea': True, 'cumulative': False, 'cumulatedStart': False})
    data.update(extra)
    return data


def match(pairs, offset=None):
    """Привязка фильтров к полям источника: {фильтр: (путь, тип)}."""
    out = {}
    for fid, (chain, ftype) in pairs.items():
        out[fid] = {'chain': chain, 'type': ftype}
        if offset is not None and ftype in ('date', 'datetime'):
            out[fid]['offset'] = offset
    return out


def both(d, name, model, domain, measures, pairs):
    """Две сводные: за выбранный период и за предыдущий такой же."""
    return (d.pivot(name, model, domain, measures, match(pairs, 0)),
            d.pivot(name + ' — прошлый период', model, domain, measures, match(pairs, -1)))


# ══════════════════════════════════════════════════════════════════════
def money():
    d = Dashboard('money', 'Мои деньги', 'coop_analytics.menu_coop_analytics_money')
    period = d.date_filter('period')
    kind = d.selection_filter('kind', 'Вид операции', 'coop.wallet.movement', 'kind')
    # У способа оплаты нет названия (`coop.wallet.method` без _rec_name —
    # движок пишет «coop.wallet.method,9»), поэтому отбор — по его виду:
    # карта, СБП, расчётный счёт.
    method = d.selection_filter('method', 'Способ оплаты', 'coop.wallet.method', 'kind')
    m = 'coop.wallet.movement'
    pairs = {period: ('date', 'date'), kind: ('kind', 'selection'),
             method: ('method_id.kind', 'selection')}
    base = [['partner_id.coop_is_me', '=', True], ['state', '=', 'confirmed']]

    inc, inc0 = both(d, 'пришло', m, base + [['amount', '>', 0]], ['amount'], pairs)
    out, out0 = both(d, 'ушло', m, base + [['amount', '<', 0]], ['amount'], pairs)
    allp, all0 = both(d, 'операции', m, base, ['__count', 'amount'], pairs)
    k_in, b_in = d.value('Пришло', '=PIVOT.VALUE(%s,"amount")' % inc, MONEY,
                         '=PIVOT.VALUE(%s,"amount")' % inc0)
    k_out, b_out = d.value('Ушло', '=-PIVOT.VALUE(%s,"amount")' % out, MONEY,
                           '=-PIVOT.VALUE(%s,"amount")' % out0)
    k_net, b_net = d.value('Сальдо', '=PIVOT.VALUE(%s,"amount")' % allp, MONEY,
                           '=PIVOT.VALUE(%s,"amount")' % all0)
    k_cnt, b_cnt = d.value('Операций', '=PIVOT.VALUE(%s,"__count")' % allp, INT,
                           '=PIVOT.VALUE(%s,"__count")' % all0)
    k_avg, b_avg = d.value('Средняя операция',
                           '=IFERROR((%s+%s)/%s,0)' % (k_in[5:], k_out[5:], k_cnt[5:]), MONEY,
                           '=IFERROR((%s+%s)/%s,0)' % (b_in[5:], b_out[5:], b_cnt[5:]))
    d.cards([
        ('Пришло', k_in, b_in, 'percentage'),
        ('Ушло', k_out, b_out, 'percentage', True),
        ('Сальдо', k_net, b_net, 'difference'),
        ('Операций', k_cnt, b_cnt, 'difference'),
        ('Средняя операция', k_avg, b_avg, 'percentage'),
    ])
    mt = match(pairs, 0)
    d.section(('Приход и расход по месяцам',
               chart('odoo_bar', m, base, ['date:month', 'kind'], 'amount', mt, legend='top')))
    d.section(('Остаток кошелька',
               chart('odoo_line', m, base, ['date:month'], 'amount', mt, stacked=False,
                     cumulative=True, cumulatedStart=True)),
              ('Операций по видам',
               chart('odoo_pie', m, base, ['kind'], '__count', mt, legend='right')))
    by_kind = d.pivot('Вид операции', m, base, ['amount', '__count'], mt, rows=['kind'],
                      sorted_by='__count')
    by_month = d.pivot('Месяц', m, base, ['amount', '__count'], mt,
                       rows=[{'fieldName': 'date', 'granularity': 'month', 'order': 'desc'}])
    d.tables(('Виды операций', by_kind), ('Последние месяцы', by_month), size=12)
    return d


def deals():
    d = Dashboard('deals', 'Мои сделки и доверие', 'coop_analytics.menu_coop_analytics_deals')
    period = d.date_filter('period')
    city = d.city_filter()
    subject = d.selection_filter('subject', 'Что передаётся', 'coop.deal', 'subject')
    m = 'coop.deal'
    pairs = {period: ('signed_on', 'date'), city: ('city', 'char'),
             subject: ('subject', 'selection')}
    rpairs = {period: ('deal_id.signed_on', 'date'), city: ('deal_id.city', 'char'),
              subject: ('deal_id.subject', 'selection')}
    mine = ['|', ['party_a_id.coop_is_me', '=', True], ['party_b_id.coop_is_me', '=', True]]
    live = mine + [['state', 'not in', ['lead', 'draft']]]

    allp, all0 = both(d, 'сделки', m, live, ['__count', 'amount', 'amount_paid'], pairs)
    done, done0 = both(d, 'завершённые', m, live + [['state', '=', 'done']], ['__count'], pairs)
    rev = d.pivot('отзывы обо мне', 'coop.deal.review', [['target_id.coop_is_me', '=', True]],
                  ['__count'], match(rpairs, 0))
    good = d.pivot('хорошие отзывы', 'coop.deal.review',
                   [['target_id.coop_is_me', '=', True], ['rating', 'in', ['4', '5']]],
                   ['__count'], match(rpairs, 0))
    trust = d.pivot('доверие', 'res.partner', [['coop_is_me', '=', True]], ['coop_trust'], {})

    k_cnt, b_cnt = d.value('Сделок', '=PIVOT.VALUE(%s,"__count")' % allp, INT,
                           '=PIVOT.VALUE(%s,"__count")' % all0)
    k_sum, b_sum = d.value('Сумма сделок', '=PIVOT.VALUE(%s,"amount")' % allp, MONEY,
                           '=PIVOT.VALUE(%s,"amount")' % all0)
    k_paid, b_paid = d.value('Оплачено', '=PIVOT.VALUE(%s,"amount_paid")' % allp, MONEY,
                             '=PIVOT.VALUE(%s,"amount_paid")' % all0)
    k_done, b_done = d.value('Завершено', '=PIVOT.VALUE(%s,"__count")' % done, INT,
                             '=PIVOT.VALUE(%s,"__count")' % done0)
    k_rev, _ = d.value('Отзывов обо мне', '=PIVOT.VALUE(%s,"__count")' % rev, INT)
    k_good, _ = d.value('Из них хороших',
                        '=IFERROR(CONCATENATE(ROUND(PIVOT.VALUE(%s,"__count")/%s*100,0),'
                        '"%% хороших"),"")' % (good, k_rev[5:]), None)
    k_trust, _ = d.value('Уровень доверия', '=PIVOT.VALUE(%s,"coop_trust")' % trust, INT)
    d.cards([
        ('Сделок', k_cnt, b_cnt, 'difference'),
        ('Сумма сделок', k_sum, b_sum, 'percentage'),
        ('Оплачено', k_paid, b_paid, 'percentage'),
        ('Завершено', k_done, b_done, 'difference'),
        ('Отзывов обо мне', k_rev, k_good, 'text'),
        ('Доверие, %', k_trust, None, 'gauge'),
    ])
    mt, rmt = match(pairs, 0), match(rpairs, 0)
    # Воронка — первым этапом обращения (владелец 08.10.2026: «обращения
    # попадают в аналитику как этап, самый первый этап, так же как и у
    # организаций лид»). Период — по «дате в воронке»: у обращения и
    # переговоров даты заключения ещё нет, и отбор по ней их выкидывал, а
    # дата создания у загруженных разом сделок одна на всех.
    fpairs = {period: ('funnel_date', 'date'), city: ('city', 'char'),
              subject: ('subject', 'selection')}
    d.section(('Воронка: от обращения до завершения',
               chart('odoo_bar', m, mine + [['state', '!=', 'cancelled']], ['state'],
                     '__count', match(fpairs, 0))))
    d.section(('Сделки по месяцам',
               chart('odoo_bar', m, live, ['signed_on:month', 'state'], '__count', mt,
                     legend='top')))
    d.section(('Что передаётся',
               chart('odoo_pie', m, live, ['subject'], 'amount', mt, legend='right')),
              ('Оценки, которые мне поставили',
               chart('odoo_bar', 'coop.deal.review', [['target_id.coop_is_me', '=', True]],
                     ['rating'], '__count', rmt)))
    d.section(('Сделки по городам',
               chart('odoo_bar', m, live, ['city'], 'amount', mt, order='DESC')),
              ('Чем закончились',
               chart('odoo_pie', m, live + [['outcome', '!=', False]], ['outcome'], '__count',
                     mt, legend='right')))
    by_way = d.pivot('Каким образом', m, live, ['__count', 'amount'], mt, rows=['way'],
                     sorted_by='amount')
    by_state = d.pivot('Состояние', m, mine, ['__count', 'amount'], mt, rows=['state'],
                       sorted_by='__count')
    d.tables(('Каким образом', by_way), ('Состояния сделок', by_state))
    return d


def projects():
    d = Dashboard('projects', 'Проекты', 'coop_projects.menu_coop_projects_root')
    period = d.date_filter('period')
    city = d.city_filter()
    topic = d.relation_filter('topic', 'Тема', 'coop.project.category')
    kind = d.selection_filter('kind', 'Вид проекта', 'coop.project', 'kind')
    m, c = 'coop.project', 'coop.project.contribution'
    pairs = {period: ('create_date', 'datetime'), city: ('city', 'char'),
             topic: ('category_id', 'many2one'), kind: ('kind', 'selection')}
    cpairs = {period: ('offered_on', 'date'), city: ('project_id.city', 'char'),
              topic: ('project_id.category_id', 'many2one'), kind: ('project_id.kind', 'selection')}
    live = [['state', 'not in', ['draft', 'cancelled']]]
    taken = [['state', 'in', ['accepted', 'released']]]

    pp, pp0 = both(d, 'проекты', m, live,
                   ['__count', 'required_total', 'contribution_total', 'readiness:avg'], pairs)
    cc, cc0 = both(d, 'вклады', c, taken, ['__count', 'value', 'partner_id:count_distinct'], cpairs)
    k_cnt, b_cnt = d.value('Проектов', '=PIVOT.VALUE(%s,"__count")' % pp, INT,
                           '=PIVOT.VALUE(%s,"__count")' % pp0)
    k_need, b_need = d.value('Нужно собрать', '=PIVOT.VALUE(%s,"required_total")' % pp, MONEY,
                             '=PIVOT.VALUE(%s,"required_total")' % pp0)
    k_got, b_got = d.value('Собрано', '=PIVOT.VALUE(%s,"contribution_total")' % pp, MONEY,
                           '=PIVOT.VALUE(%s,"contribution_total")' % pp0)
    k_rdy, b_rdy = d.value('Средняя готовность', '=PIVOT.VALUE(%s,"readiness:avg")' % pp, PCT,
                           '=PIVOT.VALUE(%s,"readiness:avg")' % pp0)
    k_con, b_con = d.value('Вкладов принято', '=PIVOT.VALUE(%s,"__count")' % cc, INT,
                           '=PIVOT.VALUE(%s,"__count")' % cc0)
    k_ppl, b_ppl = d.value('Вкладчиков', '=PIVOT.VALUE(%s,"partner_id:count_distinct")' % cc, INT,
                           '=PIVOT.VALUE(%s,"partner_id:count_distinct")' % cc0)
    d.cards([
        ('Проектов', k_cnt, b_cnt, 'difference'),
        ('Нужно собрать', k_need, b_need, 'percentage'),
        ('Собрано', k_got, b_got, 'percentage'),
        ('Готовность', k_rdy, b_rdy, 'difference'),
        ('Вкладов принято', k_con, b_con, 'difference'),
        ('Вкладчиков', k_ppl, b_ppl, 'difference'),
    ])
    mt, cmt = match(pairs, 0), match(cpairs, 0)
    # По неделям: за последний год вклады легли в два месяца, и по месяцам
    # выходило два столбца на весь экран.
    d.section(('Вклады по неделям — чем вкладываются',
               chart('odoo_bar', c, taken, ['offered_on:week', 'kind'], 'value', cmt,
                     legend='top')))
    d.section(('Проекты по темам',
               chart('odoo_bar', m, live, ['category_id'], '__count', mt, order='DESC')),
              ('Вид проекта',
               chart('odoo_pie', m, live, ['kind'], '__count', mt, legend='right')))
    d.section(('Проекты по городам',
               chart('odoo_bar', m, live, ['city'], 'contribution_total', mt, order='DESC')),
              ('В каком состоянии',
               chart('odoo_pie', m, live, ['state'], '__count', mt, legend='right')))
    top = d.pivot('Проект', m, live, ['contribution_total', 'required_total'], mt,
                  rows=['name'], sorted_by='contribution_total')
    ready = d.pivot('Проект', m, [['state', '=', 'gathering']],
                    ['readiness:avg', 'contributor_count'], mt, rows=['name'],
                    sorted_by='readiness:avg')
    d.tables(('Больше всего собрали', top), ('Ближе всего к цели — идёт сбор', ready))
    return d


def exchange():
    d = Dashboard('exchange', 'Биржа', 'coop_analytics.menu_coop_analytics_dex')
    period = d.date_filter('period', default='last_90_days')
    section = d.selection_filter('section', 'Раздел биржи', 'coop.match.fill', 'coop_section')
    asset = d.selection_filter('asset', 'Монета', 'coop.farm.pool', 'asset')
    city = d.city_filter(label='Город пула')
    f = 'coop.match.fill'
    fpairs = {period: ('date', 'datetime'), section: ('coop_section', 'selection')}
    ppairs = {period: ('date_start', 'date'), asset: ('asset', 'selection'), city: ('city', 'char')}
    tpairs = {period: ('date', 'datetime'), asset: ('asset', 'selection')}
    mine = ['|', ['maker_id.coop_is_me', '=', True], ['taker_id.coop_is_me', '=', True]]
    open_pools = [['state', 'in', ['raising', 'active']]]
    live_trades = mine + [['state', '!=', 'cancelled']]

    ff, ff0 = both(d, 'сведения', f, [], ['__count', 'coop_turnover'], fpairs)
    pools = d.pivot('пулы', 'coop.farm.pool', open_pools, ['__count', 'revenue_share:avg'],
                    match(ppairs, 0))
    tt, tt0 = both(d, 'мои обмены', 'coop.crypto.trade', live_trades, ['__count', 'total'], tpairs)
    k_cnt, b_cnt = d.value('Сделок на бирже', '=PIVOT.VALUE(%s,"__count")' % ff, INT,
                           '=PIVOT.VALUE(%s,"__count")' % ff0)
    k_vol, b_vol = d.value('Оборот', '=PIVOT.VALUE(%s,"coop_turnover")' % ff, MONEY,
                           '=PIVOT.VALUE(%s,"coop_turnover")' % ff0)
    k_pool, _ = d.value('Пулов открыто', '=PIVOT.VALUE(%s,"__count")' % pools, INT)
    # В пуле нет «доходности» (apr): условие пула — доля выручки, которую
    # проект отдаёт участникам. 20 проверяет поля сводной при загрузке, и
    # несуществующее `apr` роняло -u coop_analytics (07.10).
    k_apr, _ = d.value('Доля выручки пулам', '=PIVOT.VALUE(%s,"revenue_share:avg")' % pools,
                       '0.0[$ %]')
    k_my, b_my = d.value('Мои обмены', '=PIVOT.VALUE(%s,"__count")' % tt, INT,
                         '=PIVOT.VALUE(%s,"__count")' % tt0)
    k_myv, b_myv = d.value('Мой оборот', '=PIVOT.VALUE(%s,"total")' % tt, MONEY,
                           '=PIVOT.VALUE(%s,"total")' % tt0)
    d.cards([
        ('Сделок на бирже', k_cnt, b_cnt, 'percentage'),
        ('Оборот биржи', k_vol, b_vol, 'percentage'),
        ('Пулов открыто', k_pool, None, None),
        ('Доля выручки пулам, средняя', k_apr, None, None),
        ('Мои обмены', k_my, b_my, 'difference'),
        ('Мой оборот', k_myv, b_myv, 'percentage'),
    ])
    fmt, pmt, tmt = match(fpairs, 0), match(ppairs, 0), match(tpairs, 0)
    d.section(('Оборот биржи по неделям',
               chart('odoo_bar', f, [], ['date:week', 'coop_section'], 'coop_turnover', fmt,
                     legend='top')))
    d.section(('DEX: оборот по парам',
               chart('odoo_bar', f, [['coop_section', '=', 'dex']], ['coop_market_label'],
                     'coop_turnover', fmt, order='DESC')),
              ('Мои обмены по монетам',
               chart('odoo_pie', 'coop.crypto.trade', live_trades, ['asset'], 'total', tmt,
                     legend='right')))
    d.section(('Пулы фарминга по монетам',
               chart('odoo_bar', 'coop.farm.pool', [], ['asset', 'state'], '__count', pmt,
                     legend='top')),
              ('Сделки на бирже по дням',
               chart('odoo_line', f, [], ['date:day'], '__count', fmt, stacked=False)))
    dex = d.pivot('Пара', f, [['coop_section', '=', 'dex']], ['coop_turnover', '__count'],
                  fmt, rows=['coop_market_label'], sorted_by='coop_turnover')
    tok = d.pivot('Выпуск', f, [['coop_section', '=', 'token']],
                  ['coop_turnover', '__count'], fmt, rows=['coop_market_label'],
                  sorted_by='coop_turnover')
    d.tables(('DEX: пары по обороту', dex), ('Токеномика: выпуски по обороту', tok))
    return d


DASHBOARDS = [money, deals, projects, exchange]


def main():
    os.makedirs(OUT, exist_ok=True)
    for make in DASHBOARDS:
        d = make()
        path = os.path.join(OUT, '%s.json' % d.key)
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(d.build(), fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write('\n')
        print('%-9s %2d фильтра, %2d сводных, %2d фигур → %s' % (
            d.key, len(d.filters), len(d.pivots), len(d.figures), os.path.relpath(path)))


if __name__ == '__main__':
    main()
