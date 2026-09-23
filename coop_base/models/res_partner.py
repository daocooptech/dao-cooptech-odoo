# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    """Тип организации.

    Одним `is_company` не обойтись: кооператив, рабочая группа платформы и
    обычная компания живут по разным правилам, и права выдаются по-разному.
    Тип хранится у партнёра, а не у членства: он свойство организации, а не
    отношений с ней.
    """
    _inherit = 'res.partner'

    # Правовая форма — ссылка на справочник, а не перечисление в коде
    # (решение владельца от 2026-09-01). От формы зависят правила: кто
    # может быть пайщиком, кто вправе выпускать цифровые права, по какому
    # закону организация вообще существует. В перечислении эти правила
    # пришлось бы держать в коде, в справочнике их правит юрист.
    coop_legal_form_id = fields.Many2one(
        'coop.legal.form', string='Правовая форма',
        index=True, ondelete='restrict', tracking=True)
    coop_legal_form_group_id = fields.Many2one(
        'coop.legal.form.group', string='Группа форм',
        related='coop_legal_form_id.group_id', store=True, index=True)
    coop_is_cooperative = fields.Boolean(
        string='Кооперативная организация',
        related='coop_legal_form_id.is_cooperative', store=True)

    # Специализация одна на людей и организации: и человек, и кооператив
    # отвечают на один вопрос — чем занимаются. Разводить это на два поля
    # значит немедленно получить две несходящиеся группировки в каталогах.
    coop_specialization_id = fields.Many2one(
        'coop.specialization', string='Специализация',
        index=True, ondelete='restrict')
    coop_specialization_category_id = fields.Many2one(
        'coop.specialization.category', string='Сфера деятельности',
        related='coop_specialization_id.category_id', store=True, index=True)

    # Специализаций у человека несколько (решение 381, исполняющее
    # решение 71). Люди редко умеют что-то одно, и кооперация держится
    # ровно на этом: тот же человек нужен в одном проекте столяром, в
    # другом водителем. Одна полка на человека — упрощение, которое
    # прячет самое ценное.
    #
    # Одиночное поле выше осталось **главной** специализацией: по ней
    # подписана карточка и идёт сортировка. Убрать его значило бы
    # ответить «чем вы занимаетесь» списком из пяти строк — а человек
    # ждёт одного слова.
    coop_specialization_ids = fields.Many2many(
        'coop.specialization', 'coop_partner_specialization_rel',
        'partner_id', 'specialization_id', string='Все специализации',
        help='Чем ещё занимается. По каждой человек попадает на свою '
             'полку каталога.')
    coop_specialization_category_ids = fields.Many2many(
        'coop.specialization.category',
        'coop_partner_spec_category_rel', 'partner_id', 'category_id',
        string='Сферы деятельности', compute='_compute_spec_categories',
        store=True, index=True,
        help='Сферы всех специализаций. По ним строятся полки каталога.')

    # Признак участника и доверие — общие для людей и организаций: в
    # каталог попадают и те и другие, и доверие считается по одним и тем
    # же завершённым сделкам. Держать их в модуле людей значит закрыть их
    # для организаций, которые о модуле людей ничего не знают.
    @api.depends('coop_specialization_ids.category_id',
                 'coop_specialization_id.category_id')
    def _compute_spec_categories(self):
        """Сферы всех специализаций, включая главную.

        Главная входит в список всегда, даже если в множественное поле её
        не добавили: иначе человек, у которого заполнена только она,
        пропал бы с витрины вовсе — а до множественного поля он там был.
        """
        for record in self:
            specializations = (record.coop_specialization_ids
                               | record.coop_specialization_id)
            record.coop_specialization_category_ids =                 specializations.category_id

    @api.onchange('coop_specialization_ids')
    def _onchange_specializations(self):
        """Главная берётся из списка, если её ещё не выбрали.

        Без этого человек заполняет список, сохраняет — и видит карточку
        без специализации, потому что главная осталась пустой. Сам он о
        существовании двух полей не знает и знать не должен.
        """
        for record in self:
            if not record.coop_specialization_id and record.coop_specialization_ids:
                record.coop_specialization_id = record.coop_specialization_ids[:1]

    coop_is_participant = fields.Boolean(
        string='Участник платформы', default=False, index=True,
        help='Человек или организация зарегистрированы на платформе и видны '
             'в каталоге. Контакт без этого признака остаётся обычным '
             'контактом и в каталог не попадает.')

    # ── Доверие ─────────────────────────────────────────────────────────
    #
    # Пока поле вводится руками: формулу согласует coop-economist, и она
    # заведомо сложнее числа. Известно уже сейчас, что в знаменатель должны
    # попадать все завершённые сделки, а не только оценённые, иначе выгодно
    # молчать после плохой; и что считать доверие должен каждый узел сам из
    # полученных подписанных отзывов — значит числа у разных узлов будут
    # разными. Ставить сюда «правильную» формулу до её согласования —
    # значит потом переписывать данные, а не только код.
    # Доверие — доля сделок, по которым о человеке отозвались
    # положительно, от всех его завершённых сделок. Механика
    # владельца от 15 сентября 2026: «всего было 35 сделок, а 33 из
    # них положительные, отсюда процент считается».
    #
    # Числа поддерживает модуль сделок по событиям — завершению
    # сделки и появлению отзыва. Руками их больше не вводят: число,
    # по которому решают, иметь ли с человеком дело, не должно
    # зависеть от того, кто его вписал.
    coop_trust = fields.Integer(
        string='Уровень доверия, %', default=0, readonly=True,
        help='Доля положительных отзывов о человеке от числа его '
             'завершённых сделок.')
    coop_deals_done = fields.Integer(
        string='Завершённых сделок', default=0, readonly=True)
    coop_deals_reviewed = fields.Integer(
        string='Сделок с отзывом', default=0, readonly=True,
        help='Завершённые сделки, по которым о человеке отозвались. '
             'Знаменатель доверия: молчание второй стороны не должно '
             'снижать оценку тому, кто ничего не сделал.')
    coop_deals_positive = fields.Integer(
        string='Из них с положительным отзывом', default=0, readonly=True,
        help='Отзыв о человеке на «хорошо» или «отлично».')

    # «О себе» — строка статуса, а не статья.
    #
    # Стояло штатное `comment` — поле Html, а вместе с ним весь редактор
    # Odoo: вставка картинок и видео, загрузка файлов, кнопки, оглавление,
    # оценка звёздами. На странице участника это лишнее: блок отвечает на
    # вопрос «чем занимаюсь», а не заменяет ленту и портфолио, для
    # которых на платформе есть свои разделы. Владелец 15 сентября 2026:
    # «блок о себе слишком много себе позволяет, надо просто сделать
    # текст и ограничить количество символов».
    #
    # Своё поле, а не правка `comment`: `comment` — штатное поле контакта
    # Odoo, его пишут и читают чужие модули, и менять ему тип значило бы
    # ломать их. Длина в базе — `varchar(280)`: ограничение, которое
    # нельзя обойти, минуя форму.
    coop_about = fields.Char(
        string='О себе', size=280,
        help='Короткая заметка о себе: чем занимаетесь, что умеете, чем '
             'готовы помочь. До 280 знаков.')

    # ── Поля из макета, которых у контакта Odoo нет ────────────────────
    #
    # Одной строкой каждое, а не списком записей: в макете это перечни
    # через запятую, по ним не ищут и не фильтруют, и справочник языков
    # или мессенджеров завёл бы работу по его ведению без всякой отдачи.
    coop_languages = fields.Char(
        'Языки', help='Через запятую: русский, украинский, якутский.')
    # Skype, мессенджеры, соцсети и приложения убраны 20 сентября 2026
    # вместе со значениями: перечень видов связи устаревает быстрее, чем
    # платформа обновляется, и каждый новый требовал бы своего поля.
    # Вместо перечня — свободные поля контакта (`coop.contact.line`):
    # человек сам называет, чем с ним связаться. Решение владельца 332.
    coop_contact_line_ids = fields.One2many(
        'coop.contact.line', 'partner_id', string='Способы связи',
        help='Свободные строки контактов: название и значение.')

    # Право править карточку — отдельным полем, а не проверкой при
    # сохранении. Владелец 16 сентября 2026 об аукционах: «ты даёшь
    # возможность править поля, а потом при сохранении выводишь ошибку».
    # На странице организации было ровно так: карандаши видели все,
    # а запись правило пускало только своих.
    coop_can_edit_card = fields.Boolean(
        string='Могу править карточку', compute='_compute_coop_can_edit_card',
        help='Своя карточка и карточки организаций с полномочием на страницу.')

    # ── Что показывать на своей странице ─────────────────────────────
    #
    # Пять переключателей, а не один «закрытый профиль»: человек охотно
    # показывает, что умеет, и не охотно — сколько у него денег. Каждый
    # относится к своей полосе страницы, и каждый действует сразу — полоса
    # просто не рисуется. Настройка, которая ничего не меняет, хуже её
    # отсутствия.
    #
    # По умолчанию показывается всё, кроме баланса: остаток на счету —
    # единственное, что человек обычно не готов показывать посторонним, и
    # умолчание здесь важнее свободы выбора.
    coop_show_balance = fields.Boolean(
        string='Показывать баланс', default=False,
        help='Остаток на счету виден посторонним. Сами операции не видны '
             'никогда — только вам.')
    coop_show_trust = fields.Boolean(
        string='Показывать уровень доверия', default=True)
    coop_show_deals = fields.Boolean(
        string='Показывать число сделок', default=True)
    coop_show_friends = fields.Boolean(
        string='Показывать друзей', default=True)
    coop_show_followers = fields.Boolean(
        string='Показывать подписчиков', default=True)

    # Вторая половина — контакты и личное, по макету (`settings.html`,
    # вкладка «Приватность»). Умолчания оттуда же: телефон, почта
    # и день рождения скрыты, город и способы связи показываются.
    #
    # Это видимость на странице, а не запрет чтения: каталог людей
    # читают все, и закрыть поле правилом значило бы закрыть его и
    # для поиска, и для самой карточки. Запрет чтения — отдельная
    # работа вместе с «Кто видит мою страницу».
    coop_show_phone = fields.Boolean(
        string='Показывать телефон', default=False,
        help='Стороны активной сделки видят телефон в любом случае.')
    coop_show_email = fields.Boolean(
        string='Показывать почту', default=False)
    coop_show_contacts = fields.Boolean(
        string='Показывать сайт и способы связи', default=True,
        help='Сайт и свободные строки контактов, которые вы завели сами.')
    coop_show_birthdate = fields.Boolean(
        string='Показывать день рождения', default=False,
        help='Возраст остаётся видным: по нему выбирают исполнителя, '
             'а точная дата для этого не нужна.')
    coop_show_city = fields.Boolean(
        string='Показывать город', default=True,
        help='Только город, без точного адреса.')
    coop_show_orgs = fields.Boolean(
        string='Показывать организации', default=True,
        help='Организации, в которых вы состоите.')

    coop_block_ids = fields.One2many(
        'coop.block', 'partner_id', string='Чёрный список')
    coop_is_blocked_by_me = fields.Boolean(
        string='В моём чёрном списке',
        compute='_compute_coop_is_blocked_by_me')

    @api.depends_context('uid')
    def _compute_coop_is_blocked_by_me(self):
        me = self.env.user.partner_id
        closed = set(self.env['coop.block'].sudo().search([
            ('partner_id', '=', me.id),
            ('blocked_id', 'in', self.ids),
        ]).mapped('blocked_id').ids)
        for record in self:
            record.coop_is_blocked_by_me = record.id in closed

    def action_coop_block(self):
        """Закрыть человеку дорогу к себе."""
        self.ensure_one()
        me = self.env.user.partner_id
        if self == me:
            raise UserError(_('Себя заблокировать нельзя.'))
        self.env['coop.block'].sudo().create({
            'partner_id': me.id,
            'blocked_id': self.id,
        })
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_coop_unblock(self):
        self.ensure_one()
        me = self.env.user.partner_id
        self.env['coop.block'].sudo().search([
            ('partner_id', '=', me.id),
            ('blocked_id', '=', self.id),
        ]).unlink()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    coop_notification_pref_ids = fields.One2many(
        'coop.notification.pref', 'partner_id',
        string='Настройки извещений')

    # ── Кто видит мою страницу ───────────────────────────────────────
    #
    # Три ответа из макета (`settings.html`). «Все, включая
    # незарегистрированных» и «только участники» сегодня различаются
    # только на словах: публичной витрины у платформы ещё нет, и
    # посторонний без входа не видит ничего. Выбор всё равно хранится:
    # витрина появится, а переучивать человека потом — хуже.
    #
    # Закрытая страница — это поведение страницы, а не правило чтения
    # записи. Правилом чтения карточка исчезла бы и из чужих сделок, где
    # человек сторона, и из состава организаций, и из переписки: право
    # читать контакт на платформе держит слишком многое.
    # ── Экран «смотреть все» у полки ─────────────────────────────────
    #
    # Живёт в основе, а не в модуле страницы участника: такая же
    # кнопка есть у полок карточки организации, и звать помощника
    # через голову — из модуля, от которого не зависишь, — значит
    # получить работающую кнопку только там, где рядом случайно
    # оказался соседний модуль.
    def _coop_action_context(self, action):
        """Контекст действия словарём.

        В базе он лежит строкой — так его задают в разметке, — и
        `_for_xml_id` отдаёт его как есть. `dict()` на строке падает, и
        падает молча под кнопкой, а не при загрузке модуля.
        """
        context = action.get('context') or {}
        if isinstance(context, str):
            context = safe_eval(context, {'uid': self.env.uid})
        return dict(context)

    def _coop_holdings_action(self, xml_id, domain, name, own_name=None):
        """Экран «смотреть все» у полки страницы.

        `own_name` — как этот экран называется, когда человек смотрит
        своё: «Мои друзья», а не «Друзья — Дашкевич Данил Игоревич».
        Владелец 20 сентября 2026: «вместо каталога людей тут должно
        быть мои друзья».
        """
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(xml_id)
        own = self == self.env.user._coop_acting_partner()
        if own and own_name:
            name = own_name
        action['domain'] = domain
        action['name'] = name
        context = self._coop_action_context(action)
        context.pop('search_default_published', None)
        # Полки здесь не нужны и мешают. «Смотреть все» открывает не
        # витрину раздела, а готовый список: мои друзья, мои ресурсы,
        # мои вакансии. Рубрикация на шести записях либо не собирается
        # вовсе (рубрик меньше двух — полок нет), либо разрезает шесть
        # карточек на три полки по две.
        #
        # Владелец 20 сентября 2026 об этом прямо: «почини список моих
        # друзей, по нажатию открывается каталог моих друзей (аналог
        # вк)» — то есть список, а не витрина.
        context.pop('coop_shelf_field', None)
        # Название экрана — вкладкам оболочки: они показывают подразделы
        # раздела, а человек пришёл не в раздел, а в свою выборку.
        context['coop_screen_label'] = name
        action['context'] = context
        return action

    coop_page_audience = fields.Selection(
        [('all', 'Все, включая незарегистрированных'),
         ('members', 'Только участники платформы'),
         ('links', 'Только мои связи и стороны совместных сделок')],
        string='Кто видит мою страницу', default='all', required=True)
    coop_page_visible = fields.Boolean(
        string='Страница мне видна', compute='_compute_coop_page_visible',
        search='_search_coop_page_visible')

    # Кто может мне писать. Отдельно от видимости страницы: страницу
    # человек часто показывает всем, а получать письма от кого угодно не
    # хочет. Владелец 20 сентября 2026: «если у этого участника
    # настройками приватности запрещено писать сообщение (например
    # только друзьям) то при нажатии всплывает уведомление, что
    # пользователь принимает сообщения только от друзей».
    #
    # Два ответа, а не три: «никому» на платформе, где договариваются в
    # переписке, означает выключить себя из неё целиком — для этого есть
    # чёрный список и уход с платформы.
    coop_message_audience = fields.Selection(
        [('members', 'Все участники платформы'),
         ('links', 'Только друзья и стороны совместных сделок')],
        string='Кто может мне писать', default='members', required=True)

    def coop_can_message_me(self, sender=None):
        """Может ли этот человек написать мне.

        Проверка одна на всё: и кнопка «Написать» на странице, и
        будущий отклик из каталога должны отвечать одинаково, иначе
        запрет обходится через соседний экран.
        """
        self.ensure_one()
        from_partner = sender or self.env.user.partner_id
        if not from_partner or from_partner == self:
            return True
        if 'coop.block' in self.env:
            block = self.env['coop.block'].sudo().search_count([
                ('partner_id', '=', self.id),
                ('blocked_id', '=', from_partner.id)])
            if block:
                return False
        if self.coop_message_audience != 'links':
            return True
        return self.id in self._coop_linked_to(from_partner)

    @api.depends_context('uid')
    def _compute_coop_page_visible(self):
        me = self.env.user.partner_id
        closed = self.filtered(lambda p: p.coop_page_audience == 'links'
                                 and p != me)
        linked = closed._coop_linked_to(me) if closed else set()
        for record in self:
            record.coop_page_visible = (
                record.coop_page_audience != 'links'
                or record == me
                or record.id in linked)

    def _coop_linked_to(self, partner):
        """Кто из `self` связан с человеком: дружба или общая сделка.

        Оба вопроса решаются двумя запросами на весь набор, а не по
        записи: страница открывается одна, но каталог спрашивает про
        полторы сотни разом.
        """
        if not partner:
            return set()
        linked = set()
        # Дружба и сделки живут в соседних модулях, которые зависят от
        # основы, а не наоборот. Спрашиваем их, только если они есть:
        # узел с одной основой тоже должен подниматься.
        if 'coop.friendship' not in self.env:
            return linked
        friendships = self.env['coop.friendship'].sudo().search([
            ('state', '=', 'accepted'),
            '|',
            '&', ('requester_id', '=', partner.id),
            ('addressee_id', 'in', self.ids),
            '&', ('addressee_id', '=', partner.id),
            ('requester_id', 'in', self.ids),
        ])
        for link in friendships:
            other = (link.addressee_id if link.requester_id == partner
                      else link.requester_id)
            linked.add(other.id)
        if 'coop.deal' not in self.env:
            return linked
        deals = self.env['coop.deal'].sudo().search([
            '|',
            '&', ('party_a_id', '=', partner.id), ('party_b_id', 'in', self.ids),
            '&', ('party_b_id', '=', partner.id), ('party_a_id', 'in', self.ids),
        ])
        for deal in deals:
            other = (deal.party_b_id if deal.party_a_id == partner
                      else deal.party_a_id)
            linked.add(other.id)
        return linked

    def _search_coop_page_visible(self, operator, value):
        """Отбор по видимости — для каталога.

        Вычисляемое поле без хранения само по себе в домен не годится;
        здесь считается множество закрытых страниц, которые смотрящему
        не положены, и они исключаются по номеру.
        """
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise NotImplementedError
        visible = (operator == '=') == value
        me = self.env.user.partner_id
        closed = self.sudo().search([('coop_page_audience', '=', 'links')])
        closed = closed.filtered(lambda p: p != me)
        linked = closed._coop_linked_to(me)
        hidden = [p.id for p in closed if p.id not in linked]
        return [('id', 'not in', hidden)] if visible else [('id', 'in', hidden)]

    coop_accepts_my_message = fields.Boolean(
        string='Принимает моё письмо',
        compute='_compute_coop_accepts_my_message',
        search='_search_coop_accepts_my_message',
        help='Учитывает настройку «Кто может мне писать» и чёрный список.')

    @api.depends_context('uid')
    def _compute_coop_accepts_my_message(self):
        for record in self:
            record.coop_accepts_my_message = record.coop_can_message_me()

    def _search_coop_accepts_my_message(self, operator, value):
        """Отбор по тому, кому я могу написать.

        Нужен панели «Добавить диалог» в разделе «Сообщения»: если
        запрет проверять только у кнопки «Написать», он обходится
        соседним экраном за два щелчка.
        """
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise NotImplementedError
        accepts = (operator == '=') == value
        me = self.env.user.partner_id
        closed = self.sudo().search([('coop_message_audience', '=', 'links')])
        closed = closed.filtered(lambda p: p != me)
        linked = closed._coop_linked_to(me)
        forbidden = {p.id for p in closed if p.id not in linked}
        if 'coop.block' in self.env and me:
            for block in self.env['coop.block'].sudo().search(
                    [('blocked_id', '=', me.id)]):
                forbidden.add(block.partner_id.id)
        forbidden = list(forbidden)
        return ([('id', 'not in', forbidden)] if accepts
                else [('id', 'in', forbidden)])

    coop_profile_hidden = fields.Boolean(
        string='Профиль скрыт', default=False, copy=False,
        help='Скрытого участника не показывает каталог «Люди». Его '
             'объявления, сделки и переписка остаются на месте.')

    # ── Тихие часы ───────────────────────────────────────────────────
    #
    # Извещения на платформе копятся всегда — они никого не будят.
    # Тихие часы держат письма: ночное письмо о ставке будит телефон, а
    # утром оно прочитается ровно так же.
    coop_quiet_hours = fields.Boolean(
        string='Тихие часы', default=True,
        help='Ночью письма не отправляются — они уходят утром.')
    coop_quiet_from = fields.Float(
        string='Тишина с', default=22.0)
    coop_quiet_to = fields.Float(
        string='Тишина до', default=8.0)

    @api.depends_context('uid')
    def _compute_coop_can_edit_card(self):
        allowed = self.env.user.coop_site_partner_ids
        for record in self:
            record.coop_can_edit_card = record in allowed

    def action_coop_show_contacts(self):
        """Показать контакты участника.

        В макете это кнопка «Показать контакты» на карточке навыка и на
        объявлении: телефон и почта не выставлены сразу, а открываются по
        нажатию. Смысл не в защите — на платформе все свои, — а в том,
        что карточка отвечает на вопрос «что человек предлагает», и
        строка телефона в ней спорит с этим за внимание.

        Отдельным окном, а не переходом на страницу участника: человек
        смотрит объявление и хочет позвонить, а не уходить со страницы.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Контакты: %s') % self.display_name,
            'res_model': 'res.partner',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('coop_base.view_coop_contacts_dialog').id,
                       'form')],
            'target': 'new',
        }

    def init(self):
        """Перенести написанное в «О себе» из штатного комментария.

        Разметку снимаем: поле стало текстовым, и хранить в нём `<p>` —
        значит показывать человеку его собственные теги. Переносим
        только тем, у кого своё поле ещё пусто, поэтому повторный запуск
        ничего не портит.
        """
        super().init()
        self.env.cr.execute("""
            SELECT id, comment FROM res_partner
            WHERE comment IS NOT NULL AND comment <> ''
              AND (coop_about IS NULL OR coop_about = '')
        """)
        lines = self.env.cr.fetchall()
        if not lines:
            return
        for identifier, markup in lines:
            text = html2plaintext(markup or '').strip()
            if not text:
                continue
            self.env.cr.execute(
                "UPDATE res_partner SET coop_about = %s WHERE id = %s",
                (text[:280], identifier))
        _logger.info('«О себе»: перенесено из комментария %s записей',
                     len(lines))
        self._coop_fill_privacy_defaults()

    def _coop_fill_privacy_defaults(self):
        """Умолчания приватности — тем, кто заведён до нового поля.

        `default` действует только на новые записи: у старых в
        столбце остаётся NULL, а он читается как «нет». Для города,
        способов связи и организаций это означало бы, что новое поле
        одним обновлением опустошило бы карточки всех участников
        разом.
        """
        enabled = ('coop_show_trust', 'coop_show_deals', 'coop_show_friends',
                    'coop_show_followers', 'coop_show_contacts',
                    'coop_show_city', 'coop_show_orgs')
        disabled = ('coop_show_balance', 'coop_show_phone',
                      'coop_show_email', 'coop_show_birthdate')
        for value, field_names in ((True, enabled), (False, disabled)):
            for field in field_names:
                self.env.cr.execute(
                    'UPDATE res_partner SET %s = %%s WHERE %s IS NULL'
                    % (field, field), (value,))


    def _message_get_suggested_recipients_batch(self, *args, **kwargs):
        """Лента карточки не рассылает писем — и адресатов не предлагает.

        Штатный чаттер считает записи в ленте письмами и подбирает к ним
        получателей. У кого из них нет почты, о том он спрашивает прямо
        в окне: «Какой адрес электронной почты у АНО «Чистый город»?» —
        и предлагает вписать. Владелец 15 сентября 2026 спросил об этом
        прямо: почему платформа спрашивает почту людей и организаций, к
        которым он не имеет отношения.

        Спрашивать незачем, и вписать всё равно нельзя: правило
        `rule_partner_write_own` разрешает править только свою карточку
        и карточки организаций, которым человек доверен. Посторонний
        получил бы отказ в правах — то есть приглашение вело в тупик.

        На платформе лента карточки — это стена, а не переписка.
        Написать человеку или организации можно кнопкой «Написать», она
        ведёт в сообщения. Поэтому получателей здесь нет вовсе.

        Словарь по номерам записей, а не список. Штатный
        `_message_get_suggested_recipients` берёт из ответа `[self.id]`
        (`mail/models/models.py:642`), и пустой список валил открытие
        любой карточки участника: `IndexError: list index out of range`
        в `/mail/data`. Проверено на бою 15 сентября 2026 — это моя
        ошибка, и цена ей была страница целиком.
        """
        return {record.id: [] for record in self}

    def coop_power_holders(self, code):
        """Люди, которым организация поручила это полномочие.

        Для человека — он сам: у человека полномочий нет, он действует за
        себя.

        Зачем нужно. У организации нет учётной записи (см.
        `res.users`), а она бывает стороной сделки, хозяином объявления,
        получателем извещения. Всюду, где «действует организация», на
        самом деле действует человек, которому она это поручила, — и
        разворачивать организацию в людей надо одинаково во всех этих
        местах. Двумя копиями такого правила они разойдутся на первой же
        правке.

        Если полномочие не поручено никому, возвращается пусто: это не
        ошибка, а правда — организация только заведена, состава ещё нет.
        Что делать дальше, решает вызывающий: извещение уходит тому, кто
        ведёт состав, а вот в переписку сажать некого.
        """
        Membership = self.env['coop.membership'].sudo()
        people = self.env['res.partner']
        for record in self:
            if not record.is_company:
                people |= record
                continue
            memberships = Membership.search([
                ('organization_id', '=', record.id),
                ('state', '=', 'active'),
            ])
            people |= memberships.filtered(
                lambda m: code in m.power_ids.mapped('code')).mapped('partner_id')
        return people
