# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

_CYRILLIC = re.compile('[А-Яа-яЁё]')


class CoopExtension(models.Model):
    """Расширение платформы в каталоге.

    Каталог расширений — это витрина над штатным списком приложений Odoo, а
    не его замена. Технически расширение остаётся обычным модулем: кнопка
    «Подключить» ставит именно его. Витрина нужна затем, что штатный список
    говорит на языке разработчика (технические имена, зависимости, версии),
    а кооператору нужно понимать, что он получит и во сколько это обойдётся.

    Отсюда два раздела: **установленные** — то, чем организация уже
    пользуется, и **общий каталог** — всё доступное, включая чужие
    расширения. Разработчик со стороны публикует своё расширение и сам
    назначает условия: бесплатно, помесячно, за год или единовременно
    навсегда.
    """
    _name = 'coop.extension'
    _description = 'Расширение платформы'
    _inherit = ['mail.thread']
    _order = 'sequence, name'

    name = fields.Char(string='Название', required=True, translate=True)
    sequence = fields.Integer(default=10)
    summary = fields.Char(
        string='Коротко', required=True, translate=True,
        help='Одна фраза о том, что расширение даёт участнику. '
             'Не «модуль учёта складских остатков», а «видно, сколько '
             'ресурса свободно, а сколько уже обещано по сделкам».')
    description = fields.Html(string='Описание', translate=True)

    category = fields.Selection([
        ('accounting', 'Учёт'),
        ('process', 'Процессы'),
        ('sales', 'Сбыт'),
        ('finance', 'Финансы'),
        ('community', 'Сообщество'),
        ('integration', 'Интеграции'),
        ('localization', 'Локализации'),
    ], string='Раздел', required=True, default='process')

    # Откуда модуль (решение 463): коробка движка, модули рабочей группы,
    # мировой каталог apps.odoo.com. Сторонние — витрина и ссылка: их кода
    # на платформе нет, «Подключить» у них не бывает.
    source = fields.Selection([
        ('odoo', 'Odoo'),
        ('cooptech', 'DAO COOPTECH'),
        ('third', 'Сторонние приложения'),
    ], string='Источник', required=True, default='odoo', index=True)
    store_url = fields.Char(string='Страница в магазине Odoo')
    vendor = fields.Char(
        string='Разработчик',
        help='Автор модуля, как он подписан в манифесте или в магазине.')
    downloads = fields.Integer(string='Скачиваний')

    # Значок раздела — чтобы карточка расширения читалась как остальные
    # каталоги: слева квадрат с символом, а не пустое место. Фотографии
    # у модуля нет и быть не может, но геометрия одна.
    ICONS = {'accounting': '🧾', 'process': '⚙️', 'sales': '🛍',
             'finance': '💳', 'community': '🏘️', 'integration': '🔌',
             'localization': '🌐'}

    icon = fields.Char(string='Значок', compute='_compute_icon')

    @api.depends('category')
    def _compute_icon(self):
        for record in self:
            record.icon = self.ICONS.get(record.category, '⚙️')

    # ── Кто автор ───────────────────────────────────────────────────────
    author_id = fields.Many2one(
        'res.partner', string='Автор',
        help='Кто опубликовал расширение. Своё оно или стороннее — видно по '
             'этому полю, а не по мелкому шрифту.')
    is_official = fields.Boolean(
        string='Расширение платформы', default=False,
        help='Сделано рабочей группой платформы. Стороннее расширение этим '
             'признаком не отмечается — участник должен понимать, у кого '
             'спрашивать, если что-то пошло не так.')

    # ── Связь с настоящим модулем Odoo ──────────────────────────────────
    module_name = fields.Char(
        string='Технический модуль',
        help='Имя модуля Odoo. Пусто — значит расширение ещё не готово к '
             'установке и показывается как заявленное.')
    module_id = fields.Many2one('ir.module.module', string='Модуль',
                                compute='_compute_module', store=True)
    module_state = fields.Selection(
        related='module_id.state', string='Состояние модуля', store=True)
    # Как в Odoo (владелец 19.10.2026: «модули и плагины надо сделать как в
    # одоо»): расширение — модуль-приложение (`application` в манифесте),
    # у него свой раздел и пункт в меню. Остальное — плагины: они работают
    # внутри других разделов, пункта меню у них нет, и «Подключить» им не
    # нужно. Раньше подключить можно было любой модуль, и на плагине
    # человек получал «нет своего раздела».
    kind = fields.Selection([
        ('app', 'Расширение'),
        ('plugin', 'Плагин'),
    ], string='Вид', compute='_compute_kind', store=True, index=True)
    is_installed = fields.Boolean(
        string='Подключено', compute='_compute_module', store=True)

    # ── Условия ─────────────────────────────────────────────────────────
    #
    # Экономику назначает автор, а не платформа. Плата за расширение — это
    # отношения участника с его автором; платформа не становится стороной
    # этих отношений и не берёт долю по умолчанию.
    pricing = fields.Selection([
        ('free', 'Бесплатно'),
        ('month', 'Помесячно'),
        ('year', 'За год'),
        ('once', 'Единовременно, навсегда'),
    ], string='Условия', required=True, default='free')
    price = fields.Monetary(string='Цена', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)
    price_label = fields.Char(compute='_compute_price_label',
                              string='Стоимость')

    publication_state = fields.Selection([
        ('draft', 'Черновик'),
        ('review', 'На проверке'),
        ('published', 'В каталоге'),
        ('archived', 'Снято'),
    ], string='Публикация', default='draft', required=True, tracking=True)

    color = fields.Integer(string='Цвет')

    # И от состояния модуля, а не только от имени: модуль ставят после того,
    # как карточка заведена, и без этой зависимости «Подключено» оставалось
    # ложью — на копии боевой так стояли 7 карточек, среди них `project`
    # (18.10.2026: «Управление проектами» в меню организации висело
    # «устанавливается»).
    @api.depends('module_name', 'module_id.state')
    def _compute_module(self):
        modules = self.env['ir.module.module'].sudo()
        for record in self:
            module = modules.search([('name', '=', record.module_name)], limit=1) \
                if record.module_name else modules.browse()
            record.module_id = module
            record.is_installed = module.state == 'installed' if module else False

    @api.depends('source', 'module_id.application')
    def _compute_kind(self):
        for record in self:
            # Стороннее из магазина — витрина приложений apps.odoo.com.
            # Заявленное без модуля — тоже расширение: его заявляют ради
            # раздела, а не ради добавки к чужому.
            if record.source == 'third' or not record.module_id:
                record.kind = 'app'
            else:
                record.kind = 'app' if record.module_id.application else 'plugin'

    @api.depends('pricing', 'price', 'currency_id')
    def _compute_price_label(self):
        suffix = {'month': ' в месяц', 'year': ' в год', 'once': ' навсегда'}
        for record in self:
            if record.pricing == 'free':
                record.price_label = 'Бесплатно'
            elif not record.price:
                record.price_label = 'Цена не указана'
            else:
                amount = '{:,.0f}'.format(record.price).replace(',', ' ')
                record.price_label = '%s %s%s' % (
                    amount, record.currency_id.symbol or '',
                    suffix.get(record.pricing, ''))

    def action_install(self):
        """Подключить расширение — то есть поставить настоящий модуль Odoo.

        Ставит модуль в общую базу платформы, поэтому — только рабочая
        группа платформы и администратор (решение 463: установка — после
        одобрения всей рабочей группы). Пока каталог состоял из двадцати
        отобранных модулей, кнопку видели все; с коробкой движка в каталоге
        любой участник мог бы поставить на боевую любой из шестисот.
        """
        self.ensure_one()
        user = self.env.user
        if not (user.has_group('base.group_system')
                or user.has_group('coop_base.group_coop_platform')):
            raise UserError(
                'Модуль ставится в общую базу платформы, поэтому подключает '
                'его рабочая группа платформы после проверки кода.')
        if self.source == 'third':
            raise UserError(
                'Стороннего приложения на платформе нет — это витрина магазина '
                'Odoo. Откройте его страницу в магазине.')
        if not self.module_id:
            raise UserError(
                'Это расширение пока заявлено, но не готово к установке: '
                'технический модуль для него не указан.')
        self.module_id.sudo().button_immediate_install()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_open_module(self):
        self.ensure_one()
        if not self.module_id:
            raise UserError('У расширения нет технического модуля.')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ir.module.module',
            'res_id': self.module_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_store(self):
        self.ensure_one()
        if not self.store_url:
            raise UserError('У приложения нет страницы в магазине.')
        return {'type': 'ir.actions.act_url', 'url': self.store_url,
                'target': 'new'}

    # ── Каталог из трёх источников (решение 463, кусок 1) ───────────────
    #
    # Разделы магазина и категорий движка — к шести разделам каталога.
    # Ключ — первое слово категории («Sales/Point of Sale» → «Sales»).
    CATEGORY_MAP = {
        'Accounting': 'accounting', 'Invoicing': 'accounting',
        'Payment Providers': 'finance', 'Banking': 'finance',
        'Sales': 'sales', 'Point of Sale': 'sales', 'Website': 'sales',
        'eCommerce': 'sales', 'CRM': 'sales', 'Marketing': 'sales',
        'Email Marketing': 'sales', 'Live Chat': 'sales',
        'Discuss': 'community', 'Events': 'community',
        'eLearning': 'community', 'Productivity': 'community',
        'Social Network': 'community', 'Communication': 'community',
        'Account Charts': 'localization', 'Localization': 'localization',
        'EDI': 'localization',
        'Technical': 'integration', 'Technical Settings': 'integration',
        'Tools': 'integration', 'Extra Tools': 'integration',
        'Connector': 'integration', 'Dashboard': 'integration',
        'Uncategorized': 'integration', 'Theme': 'integration',
    }
    # Это не товар: внутренности движка и тесты.
    SKIP_CATEGORIES = ('Hidden', 'Tests')

    @api.model
    def _coop_category_of(self, name):
        head = (name or '').split('/')[0].strip()
        return self.CATEGORY_MAP.get(head, 'process')

    @api.model
    def _coop_sync_catalog(self):
        """Дополнить каталог модулями коробки, рабочей группы и магазина.

        Идёт при каждом обновлении модуля. Добавляет недостающее по имени
        модуля и проставляет источник у уже заведённых; описания, условия
        и снятие с публикации, сделанные руками, не трогает.
        """
        existing = {rec.module_name: rec for rec in
                    self.sudo().with_context(active_test=False).search(
                        [('module_name', '!=', False)])}
        vals_list = []
        modules = self.env['ir.module.module'].sudo().with_context(lang='en_US')
        for module in modules.search([]):
            # Названия категории и её родителей, от своей к корню: в Odoo 20
            # у категории модуля нет `complete_name`, а раздел решает
            # ближайшее известное название («Account Charts» под «Accounting»
            # — локализация, а не учёт).
            names, cat = [], module.category_id
            while cat:
                names.append(cat.name)
                cat = cat.parent_id
            category = next((n for n in names if n in self.CATEGORY_MAP),
                            names[-1] if names else '')
            source = 'cooptech' if module.name.startswith('coop_') else 'odoo'
            rec = existing.get(module.name)
            if rec:
                if rec.source != 'third' and rec.source != source:
                    rec.source = source
                continue
            if (set(names) & set(self.SKIP_CATEGORIES)
                    or module.name.startswith('test_')):
                continue
            vals_list.append({
                'name': module.shortdesc or module.name,
                'summary': module.summary or module.shortdesc or module.name,
                'module_name': module.name,
                'source': source,
                'vendor': module.author or False,
                'category': self._coop_category_of(category),
                'is_official': source == 'cooptech',
                'publication_state': 'published',
                'sequence': 50,
            })
            existing[module.name] = True
        # Карточки, у которых признак «стоит» разошёлся с модулем, —
        # пересчитать (см. `_compute_module`).
        stale = self.sudo().with_context(active_test=False).search(
            [('module_id', '!=', False)]).filtered(
            lambda r: r.is_installed != (r.module_id.state == 'installed'))
        if stale:
            self.env.add_to_compute(self._fields['is_installed'], stale)
            stale.flush_recordset(['is_installed'])
        vals_list += self._coop_store_vals(existing)
        # Русские названия коробки (владелец 19.10.2026: «некоторые модули
        # из коробки не переведены на русский»). Перевод движка покрывает
        # 49 названий из 565, поэтому свой словарь. Правим только то, что
        # ещё латиницей: название, переписанное руками, не трогаем.
        names = self._coop_ru_names()
        for vals in vals_list:
            ru = names.get(vals.get('module_name'))
            if ru and vals.get('source') == 'odoo':
                vals.update(name=ru[0], summary=ru[1])
        for name, rec in existing.items():
            ru = names.get(name)
            if not ru or rec is True or rec.source != 'odoo':
                continue
            values = {}
            if not _CYRILLIC.search(rec.name or ''):
                values['name'] = ru[0]
            if not _CYRILLIC.search(rec.summary or ''):
                values['summary'] = ru[1]
            if values:
                rec.with_context(tracking_disable=True).write(values)
        if vals_list:
            # Без записей «создано» в ленте: шестьсот сообщений о том, что
            # каталог наполнен, никому не нужны.
            self.sudo().with_context(tracking_disable=True, mail_create_nolog=True,
                                     mail_notrack=True).create(vals_list)
        return len(vals_list)

    @api.model
    def _coop_drop_plugin_menus(self):
        """Убрать из меню плагины, подключённые до разделения.

        До 19.10.2026 «Подключить» было у любого модуля, и плагин вставал
        в меню пунктом, который никуда не ведёт или ведёт в чужой раздел.
        """
        plugins = self.sudo().search([('kind', '=', 'plugin')])
        items = self.env['coop.sidebar.item'].sudo().search(
            [('extension_id', 'in', plugins.ids)])
        conns = self.env['coop.extension.connection'].sudo().search(
            [('extension_id', 'in', plugins.ids)])
        items.write({'is_required': False})
        items.unlink()
        conns.unlink()
        return len(items) + len(conns)

    @api.model
    def _coop_ru_names(self):
        """{модуль: (название, коротко)} из `data/odoo_modules_ru.tsv`."""
        from odoo.tools.misc import file_path
        result = {}
        path = file_path('coop_extensions/data/odoo_modules_ru.tsv')
        with open(path, encoding='utf-8') as f:
            for line in f:
                parts = line.rstrip('\n').split('\t')
                if len(parts) == 3 and parts[0]:
                    result[parts[0]] = (parts[1], parts[2])
        return result

    @api.model
    def _coop_store_vals(self, existing):
        """Сторонние приложения — 200 карточек apps.odoo.com (12.10.2026).

        Файл собран сборщиком `tools/fetch_odoo_apps.py --by-category 200
        --scan 5`: поровну из 18 разделов магазина, самые скачиваемые.
        """
        import json
        from odoo.tools.misc import file_path
        path = file_path('coop_extensions/data/odoo_apps_19.jsonl')
        rub = self.env.ref('base.RUB', raise_if_not_found=False)
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        # Уже заведённые сторонние узнаются по странице в магазине: имени
        # модуля у них нет (см. ниже), а без этой сверки каждое обновление
        # модуля заводило бы все двести заново.
        seen = set(self.sudo().with_context(active_test=False).search(
            [('source', '=', 'third')]).mapped('store_url'))
        vals_list = []
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                app = json.loads(line)
                if app['url'] in seen or app['module'] in existing:
                    continue
                seen.add(app['url'])
                vals_list.append({
                    'name': app['name'],
                    'summary': app.get('summary') or app['name'],
                    # Имя модуля стороннего — для справки, не для установки:
                    # `module_name` пуст, иначе карточка искала бы его в
                    # коробке и предлагала «Подключить».
                    'description': '<p>Модуль <code>%s</code> в магазине Odoo, '
                                   'серия %s.</p>' % (app['module'], app['series']),
                    'source': 'third',
                    'store_url': app['url'],
                    'vendor': app.get('author') or False,
                    'downloads': app.get('downloads') or 0,
                    'category': self._coop_category_of(app.get('category')),
                    'pricing': 'once' if app.get('is_paid') else 'free',
                    'price': app.get('price') or 0.0,
                    'currency_id': (usd or rub or self.env.company.currency_id).id,
                    'publication_state': 'published',
                    'sequence': 90,
                })
        return vals_list

    def action_publish(self):
        self.write({'publication_state': 'published'})

    def action_archive_listing(self):
        self.write({'publication_state': 'archived'})


class CoopExtensionCatalogFilters(models.Model):
    """Панель отбора каталога расширений.

    Та же панель, что у остальных каталогов платформы: набор полей
    объявляет сам раздел, а тема рисует его и считает по нему записи.
    Штатная панель Odoo здесь не годится — она берёт фиксированный
    список полей из разметки и работает только со ссылками и списками
    значений, без диапазона цены.

    Что отбирают в каталоге расширений: раздел, условия, цену и
    состояние — подключено ли, чьё, готово ли к установке. Состояние
    вынесено в быстрые значки: это ярлыки к тому, что человек и так
    видит на карточке, и нажимаются они чаще, чем открывается список
    выбора.
    """

    _inherit = 'coop.extension'

    def _coop_catalog_filters(self, domain):
        def choice(name):
            return [{'value': code, 'label': label}
                    for code, label in self._fields[name].selection]

        return [
            {'code': 'source', 'label': 'Источник',
             'hint': 'Коробка Odoo, модули DAO COOPTECH или магазин Odoo — '
                     'сторонние приложения там только витриной и ссылкой.',
             'widget': 'select', 'field': 'source', 'placeholder': 'Любой',
             'options': choice('source')},
            {'code': 'category', 'label': 'Раздел',
             'hint': 'Учёт, процессы, сбыт, финансы, сообщество, интеграции.',
             'widget': 'select', 'field': 'category', 'placeholder': 'Любой',
             'options': choice('category')},
            {'code': 'pricing', 'label': 'Условия',
             'hint': 'Условия назначает автор расширения, а не платформа.',
             'widget': 'select', 'field': 'pricing', 'placeholder': 'Любые',
             'options': choice('pricing')},
            {'code': 'price', 'label': 'Цена, ₽',
             'hint': 'Пустое поле — без ограничения. У бесплатных цена нулевая, '
                     'и «от» их отсекает.',
             'widget': 'range', 'field': 'price'},
            {'code': 'quick', 'label': 'Быстрые фильтры', 'widget': 'quick',
             'options': [
                 # Подключено — в меню текущего лица (решение 468).
                 {'value': 'installed', 'label': '✓ Подключено',
                  'domain': [('coop_connected', '=', True)]},
                 {'value': 'available', 'label': '⬇ Можно подключить',
                  'domain': [('coop_connected', '=', False),
                             ('module_name', '!=', False),
                             ('kind', '=', 'app')]},
                 {'value': 'planned', 'label': '🕓 Заявлено',
                  'domain': [('module_name', '=', False),
                             ('source', '!=', 'third')]},
                 {'value': 'official', 'label': '🏛 DAO COOPTECH',
                  'domain': [('source', '=', 'cooptech')]},
                 {'value': 'third', 'label': '🧩 Стороннее',
                  'domain': [('source', '=', 'third')]},
             ]},
        ]
