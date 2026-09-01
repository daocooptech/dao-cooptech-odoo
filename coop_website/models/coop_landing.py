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
SITE_MENU = [
    ('Люди', '/odoo/action-coop_people.action_coop_people'),
    ('Организации', '/odoo/action-coop_orgs.action_coop_orgs'),
    ('Вакансии', '/jobs'),
    ('Обучение', '/slides'),
    ('Сообщество', '/forum'),
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
    def setup_site(self):
        """Название, логотип и меню публичной части.

        Стандартные «Your Logo» и «Contact Us» — заглушки установщика
        Odoo. Оставлять их на первой странице платформы нельзя: посетитель
        видит незаполненный шаблон, а не проект.
        """
        website = self.env['website'].sudo().search([], limit=1)
        if not website:
            return False

        values = {'name': 'ДАО КООПЕХ'}

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

        Menu = self.env['website.menu'].sudo()
        root = Menu.search([('website_id', '=', website.id),
                            ('parent_id', '=', False)], limit=1)
        if not root:
            return True

        # Существующие пункты меню сносим и собираем заново: иначе к
        # разделам платформы добавляются «Home», «Shop» и прочие пункты
        # установщика, а порядок оказывается случайным.
        Menu.search([('parent_id', '=', root.id)]).unlink()
        for sequence, (name, url) in enumerate(SITE_MENU, start=1):
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
