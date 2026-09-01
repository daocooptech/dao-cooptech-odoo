# -*- coding: utf-8 -*-
"""Порядок пунктов главного меню — как в макете.

Решение владельца от 2026-09-01: меню платформы идёт в том же порядке, что
в прототипе (`tools/shell.html`), а всё, чего в макете нет, уходит вниз
общим списком после расширений.

Почему кодом, а не набором XML-записей с sequence. Часть пунктов — это
штатные приложения Odoo и модули Rudoo, и ссылаться на их внешние
идентификаторы из XML можно только объявив их в зависимостях модуля.
Тогда coop_base потянул бы за собой половину дистрибутива и перестал бы
ставиться на узел, где чего-то из этого нет. Здесь же отсутствующий пункт
просто пропускается.
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# Порядок из макета. Пункты, которых на платформе ещё нет, оставлены
# комментариями на своих местах: по ним видно, где появится раздел, когда
# он будет перенесён, и что пропуск в нумерации — не случайность.
MOCKUP_ORDER = [
    # (10, 'Моя страница')            — раздел ещё не перенесён
    (20, 'mail.menu_root_discuss', 'Сообщения'),
    (30, 'coop_people.menu_coop_people_root', 'Люди'),
    (40, 'coop_skills.menu_coop_skills_root', None),
    (50, 'hr_recruitment.menu_hr_recruitment_root', 'Вакансии'),
    (60, 'coop_resources.menu_coop_resources_root', None),
    (70, 'project.menu_main_pm', 'Проекты'),
    (80, 'coop_orgs.menu_coop_orgs_root', 'Организации'),
    # (90, 'Сообщества')              — раздел ещё не перенесён
    # (100, 'Кошелёк')                — раздел ещё не перенесён
    # (110, 'Сделки')                 — раздел ещё не перенесён
    # (120, 'Токеномика')             — раздел ещё не перенесён
    # (130, 'Цифровые активы')        — раздел ещё не перенесён
    # (140, 'Нематериальные активы')  — раздел ещё не перенесён

    # ── Расширения и разделы, которые в макете идут после них ──────────
    (150, 'coop_extensions.menu_coop_extensions_root', None),
    # (160, 'Целевые программы ПК')   — раздел ещё не перенесён
    # (170, 'Совместные закупки')     — раздел ещё не перенесён
    (180, 'stock.menu_stock_root', 'Склад'),
    (190, 'event.event_main_menu', 'События'),
    # (200, 'Аналитика')              — раздел ещё не перенесён
    (210, 'website_slides.website_slides_menu_root', 'Образование'),
    # (220, 'Аукционы')               — раздел ещё не перенесён
    # (230, 'Библиотеки')             — раздел ещё не перенесён
    (240, 'dms.main_menu_dms', 'Диск'),
    # (250, 'Здоровье')               — раздел ещё не перенесён
]

# Всё остальное — ниже, после расширений, общим списком. Порядок внутри
# осмысленный: сначала то, чем пользуются каждый день, потом учёт, потом
# администрирование.
BELOW_ORDER = [
    'contacts.menu_contacts',
    'coop_base.menu_coop_root',
    'sale.sale_menu_root',
    'purchase.menu_purchase_root',
    'account.menu_finance',
    'hr_timesheet.timesheet_menu_root',
    'hr.menu_hr_root',
    'website.menu_website_configuration',
    'spreadsheet_dashboard.spreadsheet_dashboard_menu_root',
    'calendar.mail_menu_calendar',
    'project_todo.menu_todo_todos',
    'utm.menu_link_tracker_root',
    'base.menu_management',
    'base.menu_administration',
]

BELOW_START = 900
BELOW_STEP = 10
# Пункты, которых нет ни в одном списке, уезжают в самый конец: это
# служебные меню вроде «Тесты», и место им там.
UNLISTED = 1100


class CoopMenuOrder(models.AbstractModel):
    _name = 'coop.menu.order'
    _description = 'Порядок главного меню'

    @api.model
    def apply(self):
        Menu = self.env['ir.ui.menu'].sudo()
        languages = self.env['res.lang'].get_installed()
        languages = [code for code, _name in languages] or ['en_US']
        placed = set()

        for sequence, xmlid, label in MOCKUP_ORDER:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if not menu:
                continue
            menu.sequence = sequence
            # Название меняем только там, где штатное приложение и есть тот
            # самый раздел макета: «Обсуждения» — это «Сообщения», «Найм» —
            # «Вакансии». Свои меню переименовывать не нужно, они и так
            # названы по макету.
            #
            # Записывать приходится в каждый язык отдельно: имя меню —
            # переводимое поле, и обычная запись легла бы только в язык
            # текущего сеанса. При установке это английский, и в русском
            # интерфейсе пункт так и остался бы «Обсуждениями».
            if label:
                for language in languages:
                    menu.with_context(lang=language).name = label
            placed.add(menu.id)

        sequence = BELOW_START
        for xmlid in BELOW_ORDER:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if not menu:
                continue
            menu.sequence = sequence
            placed.add(menu.id)
            sequence += BELOW_STEP

        rest = Menu.search([('parent_id', '=', False), ('id', 'not in', list(placed))])
        rest.write({'sequence': UNLISTED})

        _LOG = 'Порядок меню: по макету %s, ниже %s, прочих %s'
        _logger.info(_LOG, len(placed) - len(BELOW_ORDER), len(BELOW_ORDER), len(rest))
        return True
