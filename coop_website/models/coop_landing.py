# -*- coding: utf-8 -*-
"""Настройка публичной части: лендинг, название, логотип и меню сайта.

Простого переопределения `website.homepage` в XML недостаточно. Odoo
держит для каждого сайта собственную копию представления главной: как
только страницу открывают в конструкторе, появляется копия с проставленным
website_id, и отдаётся дальше именно она. Переопределение из модуля
ложится в общее представление, а на экране остаётся копия — главная
выглядит пустой, и понять почему по коду невозможно.

Поэтому лендинг ставится кодом: обходятся все представления с ключом
`website.homepage`, включая копии сайтов.
"""
import base64
import logging
import os

from odoo import api, models

_logger = logging.getLogger(__name__)

CALL = '<t name="Homepage" t-call="coop_website.coop_landing"/>'

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(os.path.dirname(HERE), 'static', 'src', 'img', 'cooptech-logo.png')

# Меню сайта — разделы платформы в том же порядке, что в макете. Пункты
# ведут в разделы, которые уже работают: обещать с публичной страницы
# то, чего нет, хуже, чем показать короткое меню.
# Заглушки установщика Odoo: пункты, которых на платформе быть не должно.
# Список закрытый — всё остальное считается добавленным осознанно.
# `/jobs` — страница «Вакансий» модуля найма Odoo: пустая, с чужим фото,
# «yourcompany» и телефоном +1 (650) 555-0187. Вакансии платформы живут в
# каталоге `coop.vacancy` (решение 439, п. 8).
INSTALLER_MENUS = {'/', '/shop', '/blog', '/aboutus', '/pricing', '/contactus',
                   '/event', '/appointment', '/library', '/jobs'}

SITE_MENU = [
    # Первым пунктом — своя страница. Её не было ни в одном меню
    # сайта, и вошедший участник, попав на лендинг, не мог попасть к
    # себе вовсе: верхнее меню вело в каталоги, а платформа
    # открывалась только по прямому адресу. Владелец указал на это
    # 15 сентября 2026.
    #
    # Пункт виден и постороннему: нажав, он попадёт на вход, а после
    # него к себе. Это честнее, чем прятать вход в платформу от
    # того, кто пришёл в неё вступать.
    ('Моя страница', '/odoo/my-page'),
    ('Люди', '/odoo/action-coop_people.action_coop_people'),
    ('Организации', '/odoo/action-coop_orgs.action_coop_orgs'),
    ('Вакансии', '/odoo/vacancies'),
    ('Обучение', '/slides'),
    ('Сообщество', '/forum'),
    # Страница живёт в модуле coop_bounty, но место в меню задаётся здесь:
    # порядок пунктов — свойство сайта целиком, и собирать его из
    # разрозненных записей значит получить случайную последовательность.
    ('Помощь проекту', '/help-project'),
]


class CoopWebsiteLanding(models.AbstractModel):
    _name = 'coop.website.landing'
    _description = 'Лендинг главной страницей'

    @api.model
    def apply(self):
        views = self.env['ir.ui.view'].sudo().with_context(active_test=False).search([
            ('key', '=', 'website.homepage'),
        ])

        changed = 0
        for view in views:
            # Уже наш лендинг — не трогаем. Это не оптимизация: правки,
            # сделанные в конструкторе, живут в копии нашего же шаблона, и
            # переписывать здесь арх заново значит терять их при каждом
            # обновлении модуля.
            if 'coop_website.coop_landing' in (view.arch_db or ''):
                continue
            view.arch = CALL
            changed += 1

        _logger.info('Лендинг главной: представлений %s, изменено %s',
                     len(views), changed)
        return True


    @api.model
    def _landing_facts(self):
        """Живые цифры лендинга (решение 438, п. 3: «без оговорки») и
        данные узла для блока «Проверьте сами».

        Считается здесь, а не выражениями в шаблоне: так проверяется
        наличие модели — у `coop_website` в зависимостях только база,
        люди и организации, остальное может быть не установлено, — и
        цифру с нулём шаблон просто не выводит («0 сделок» читается как
        поломка).
        """
        env = self.env
        Partner = env['res.partner'].sudo()

        def count(model, domain):
            if model not in env:
                return 0
            return env[model].sudo().search_count(domain)

        stats = [
            (Partner.search_count([('coop_is_participant', '=', True),
                                   ('is_company', '=', False)]), 'участников'),
            (Partner.search_count([('coop_is_participant', '=', True),
                                   ('is_company', '=', True)]),
             'организаций — кооперативы, НКО, ООО, ДАО'),
            (count('coop.community', [('state', '=', 'published')]), 'сообществ'),
            (count('coop.project', [('state', 'in', ('gathering', 'running', 'done'))]),
             'проектов'),
            (count('coop.deal', [('state', '=', 'done')]), 'завершённых сделок'),
            (count('coop.farm.pool', [('state', 'in', ('raising', 'active'))]),
             'пулов проектов'),
        ]
        facts = {
            'stats': [{'value': v, 'label': label} for v, label in stats if v],
            'legal_forms': count('coop.legal.form', []),
            'node': False,
        }
        if 'coop.fed.identity' in env:
            identity = env['coop.fed.identity'].sudo().search(
                [('state', '=', 'active')], limit=1)
            if identity and identity.head_seq >= 0:
                facts['node'] = {
                    'did': identity.did,
                    'records': identity.head_seq + 1,
                    'peers': count('coop.fed.peer', [('state', '=', 'active')]),
                }
        return facts

    @api.model
    def _legal_facts(self):
        """Реквизиты для Политики, Согласия и Правил сети (решение 438,
        п. 8). Платформа — демо (решение 443): оператор — «ДАО КООПТЕХ», а
        реквизиты, которых владелец не задал параметром
        `coop_website.legal_<ключ>`, в документах не показываются — их не
        выдумываем и не заменяем пометкой в скобках."""
        get = self.env['ir.config_parameter'].sudo().get_param
        keys = {
            'operator': 'ДАО КООПТЕХ', 'organizer': 'ДАО КООПТЕХ',
            # Реквизиты не выдумываются: пока параметр не задан, строка
            # с ним в документах не показывается (решение 443).
            'inn': '', 'ogrn': '', 'address': '',
            'email': 'bizzz.ru@gmail.com',  # решение 439, п. 2
            'dpo': '', 'rkn': '',
            'date': '06.10.2026', 'rules_effective': '',
            'dex_operator': 'ДАО КООПТЕХ',
        }
        facts = {key: get('coop_website.legal_%s' % key) or default
                 for key, default in keys.items()}
        # Ответственный за организацию обработки — сам оператор (решение
        # 440, п. 6), пока параметр не задан отдельно.
        if not get('coop_website.legal_dpo'):
            facts['dpo'] = facts['operator']
        return facts

    @api.model
    def _software_facts(self):
        """Версия движка для страницы «О программе» (решение 442).

        Берётся из deploy/engine.ref — того же файла, по которому выкатка
        ставит движок, — а не пишется руками: метка, прописанная в шаблоне,
        разошлась бы с тем, что работает. Формат файла: `<метка> <sha>`.
        Пока файла нет, работает неизменённый Odoo 19.0, и страница честно
        ведёт на его коммит.
        """
        ref = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'deploy', 'engine.ref')
        tag, sha = '', 'df0149e3'
        if os.path.exists(ref):
            with open(ref, encoding='utf-8') as fh:
                parts = fh.read().split()
            if parts:
                tag, sha = parts[0], (parts[1] if len(parts) > 1 else '')
        if tag:
            return {
                'modified': True,
                'label': tag,
                'source_url': 'https://github.com/daocooptech/odoo/tree/%s' % tag,
                'mirror_url': '/src/odoo-%s.tar.gz' % tag,
                'notice_url': 'https://github.com/daocooptech/odoo/blob/%s/NOTICE.coop' % tag,
                'sha': sha,
            }
        return {
            'modified': False,
            'label': '19.0 @ %s' % sha,
            'source_url': 'https://github.com/odoo/odoo/tree/%s' % sha,
            'mirror_url': '',
            'notice_url': '',
            'sha': sha,
        }

    @api.model
    def setup_site(self):
        """Название, логотип и меню публичной части.

        Стандартные «Your Logo» и «Contact Us» — заглушки установщика
        Odoo. Оставлять их на первой странице платформы нельзя: посетитель
        видит незаполненный шаблон, а не проект.
        """
        website = self.env['website'].sudo().search([], limit=1)
        if not website:
            return False

        values = {'name': 'ДАО КООПТЕХ'}

        # Свободная регистрация. Без неё страница `/web/signup` отвечает
        # «не найдено»: Odoo прячет её целиком, когда регистрация
        # закрыта. Общий параметр настройки при этом стоит верный —
        # решает поле сайта, и разойтись они могут незаметно.
        #
        # Платформа кооперации, на которую нельзя зарегистрироваться, —
        # это витрина, а не платформа, поэтому регистрация открыта.
        if website.auth_signup_uninvited != 'b2c':
            values['auth_signup_uninvited'] = 'b2c'

        # Логотип ставится один раз и запоминается признаком. Проверять
        # «пустой ли логотип» бесполезно: установщик Odoo кладёт туда свою
        # заглушку «Your Logo», и она никогда не пуста. А писать логотип
        # при каждом обновлении нельзя — затрём тот, что загрузили руками.
        Config = self.env['ir.config_parameter'].sudo()
        if os.path.exists(LOGO) and not Config.get_param('coop_website.logo_set'):
            with open(LOGO, 'rb') as fh:
                values['logo'] = base64.b64encode(fh.read())
            Config.set_param('coop_website.logo_set', '1')

        # Телефон и почта из установщика — «+1 555-555-5556» и адрес
        # yourcompany.example. В шапке сайта они выглядят как настоящие
        # контакты платформы, поэтому убираются.
        company = website.company_id or self.env.company
        if company.phone and '555-555' in company.phone:
            company.phone = False
        if company.email and 'yourcompany' in (company.email or ''):
            company.email = False

        website.write(values)

        # Значок вкладки сайта — логотип платформы (решение 442). У сайта
        # значок по умолчанию — байты значка Odoo, пустым он не бывает,
        # поэтому ставится один раз и запоминается признаком, как логотип:
        # загруженный руками потом не трогаем.
        if os.path.exists(LOGO) and not Config.get_param('coop_website.favicon_set'):
            with open(LOGO, 'rb') as fh:
                website.favicon = base64.b64encode(fh.read())
            Config.set_param('coop_website.favicon_set', '1')

        Menu = self.env['website.menu'].sudo()
        root = Menu.search([('website_id', '=', website.id),
                            ('parent_id', '=', False)], limit=1)
        if not root:
            return True

        # Сносятся заглушки установщика Odoo — по закрытому списку
        # адресов. Раньше здесь удалялись все пункты подряд, и это стирало
        # меню, добавленные другими нашими модулями: «Помощь проекту»
        # исчезала при каждом обновлении сайта, а причина по коду не
        # читалась.
        Menu.search([('parent_id', '=', root.id),
                     ('url', 'in', list(INSTALLER_MENUS))]).unlink()

        # Схлопывание по адресу. Установщик и наши модули заводят пункты с
        # одним и тем же адресом под разными названиями — «Курсы» и
        # «Обучение» оба ведут на /slides, — и в шапке они стоят рядом
        # как два разных раздела.
        seen = {}
        for menu in Menu.search([('parent_id', '=', root.id)], order='sequence, id'):
            if menu.url in seen:
                menu.unlink()
            else:
                seen[menu.url] = menu

        for sequence, (name, url) in enumerate(SITE_MENU, start=1):
            menu = seen.get(url)
            if menu:
                menu.write({'name': name, 'sequence': sequence * 10})
            else:
                Menu.create({
                    'name': name,
                    'url': url,
                    'parent_id': root.id,
                    'sequence': sequence * 10,
                    'website_id': website.id,
                })

        _logger.info('Публичная часть: сайт «%s», пунктов меню %s',
                     website.name, len(SITE_MENU))
        return True
