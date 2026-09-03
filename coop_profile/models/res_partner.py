# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

# Через сколько дней объявление считается залежавшимся и участнику
# предлагают его подтвердить. Тридцать — из макета; смысл в том, что
# свежие объявления стоят выше в выдаче, и подтверждение возвращает
# объявлению место, а не просто убирает напоминание.
STALE_LISTING_DAYS = 30


class ResPartner(models.Model):
    """Владения участника — то, из чего складывается «Моя страница».

    Считаются пачкой и не хранятся. Не хранятся потому, что счётчик
    зависит от того, кто смотрит: владельцу видны черновики и снятые с
    публикации объявления, постороннему — только опубликованные, и
    хранить одно число на всех тут нечего.

    Пачкой — потому что иначе на карточку уходит по запросу на каждый
    счётчик, а их восемь.
    """

    _inherit = 'res.partner'

    coop_offer_count = fields.Integer(
        string='Навыков', compute='_compute_coop_holdings')
    coop_resource_count = fields.Integer(
        string='Ресурсов', compute='_compute_coop_holdings')
    coop_vacancy_count = fields.Integer(
        string='Вакансий', compute='_compute_coop_holdings')
    coop_project_count = fields.Integer(
        string='Проектов', compute='_compute_coop_holdings')
    coop_community_count = fields.Integer(
        string='Сообществ', compute='_compute_coop_holdings')
    coop_deal_count = fields.Integer(
        string='Сделок', compute='_compute_coop_holdings')
    coop_friend_count = fields.Integer(
        string='Друзей', compute='_compute_coop_holdings')
    coop_draft_count = fields.Integer(
        string='Черновиков и снятых', compute='_compute_coop_holdings',
        help='Объявления, которых в каталоге не видно: черновики и снятые '
             'с публикации. Видно только владельцу.')

    # Обратные связи под полосы страницы. Заведены здесь, а не в каждом
    # каталоге, потому что этот модуль и так стоит поверх них всех, а
    # держать пять одинаковых объявлений в пяти местах незачем.
    coop_offer_ids = fields.One2many(
        'coop.skill.offer', 'partner_id', string='Навыки в каталоге')
    coop_resource_ids = fields.One2many(
        'coop.resource', 'owner_id', string='Ресурсы')
    coop_vacancy_ids = fields.One2many(
        'coop.vacancy', 'partner_id', string='Вакансии')
    coop_project_ids = fields.One2many(
        'coop.project', 'partner_id', string='Проекты')
    coop_community_member_ids = fields.One2many(
        'coop.community.member', 'partner_id', string='Участие в сообществах')
    coop_education_ids = fields.One2many(
        'coop.education', 'partner_id', string='Образование')
    coop_achievement_ids = fields.One2many(
        'coop.achievement', 'partner_id', string='Достижения')


    # Друзья в макете — полоса плиток. Считаются, а не хранятся: дружба
    # двусторонняя и лежит в отдельной модели, где участник может стоять
    # с любой из сторон.
    coop_friend_ids = fields.Many2many(
        'res.partner', string='Друзья', compute='_compute_coop_links')
    # Потребности — собственные объявления спроса. Отдельной сущности им
    # заводить не за чем: «ищу морковь» — это объявление, и живёт оно по
    # тем же правилам, что остальные, включая снятие с публикации.
    coop_need_ids = fields.One2many(
        'coop.resource', 'owner_id', string='Потребности',
        domain=[('listing_type', '=', 'request')])
    # Объявления, залежавшиеся в каталоге. Из них собирается напоминание
    # из макета: «висит 30 дней, всё ещё актуально?».
    coop_stale_resource_ids = fields.Many2many(
        'coop.resource', compute='_compute_coop_links',
        string='Залежавшиеся объявления')
    coop_follower_count = fields.Integer(
        string='Подписчиков', compute='_compute_coop_links')
    coop_balance = fields.Monetary(
        string='Баланс', compute='_compute_coop_links',
        currency_field='coop_balance_currency_id',
        help='Остаток кошелька. Виден только владельцу страницы.')
    coop_balance_currency_id = fields.Many2one(
        'res.currency', compute='_compute_coop_links')

    # ── Поля из макета, которых у контакта Odoo нет ────────────────────
    #
    # Одной строкой каждое, а не списком записей: в макете это перечни
    # через запятую, по ним не ищут и не фильтруют, и справочник языков
    # или мессенджеров завёл бы работу по его ведению без всякой отдачи.
    coop_languages = fields.Char(
        'Языки', help='Через запятую: русский, украинский, якутский.')
    coop_skype = fields.Char('Skype')
    coop_messengers = fields.Char(
        'Мессенджеры', help='Через запятую: Telegram, WhatsApp, Viber.')
    coop_socials = fields.Char('Социальные сети')
    coop_apps = fields.Char(
        'Приложения', help='Профили в чужих сервисах: GitHub, Habr и другие.')

    # Свёрнутый признак «страница пустая». По нему форма показывает не
    # девять пустых полос, а один блок «чего здесь ещё нет»: девять пустых
    # разделов читаются как недогрузившаяся страница, а не как приглашение
    # их заполнить.
    coop_holdings_empty = fields.Boolean(
        string='Ничего не заведено', compute='_compute_coop_holdings')

    def _compute_coop_holdings(self):
        counts = {field: {} for field in (
            'offer', 'resource', 'vacancy', 'project', 'community', 'deal',
            'friend', 'draft')}
        if self.ids:
            counts = self._coop_count_holdings()
        for record in self:
            record.coop_offer_count = counts['offer'].get(record.id, 0)
            record.coop_resource_count = counts['resource'].get(record.id, 0)
            record.coop_vacancy_count = counts['vacancy'].get(record.id, 0)
            record.coop_project_count = counts['project'].get(record.id, 0)
            record.coop_community_count = counts['community'].get(record.id, 0)
            record.coop_deal_count = counts['deal'].get(record.id, 0)
            record.coop_friend_count = counts['friend'].get(record.id, 0)
            record.coop_draft_count = counts['draft'].get(record.id, 0)
            record.coop_holdings_empty = not any((
                record.coop_offer_count, record.coop_resource_count,
                record.coop_vacancy_count, record.coop_project_count,
                record.coop_community_count, record.coop_membership_count,
            ))

    def _compute_coop_links(self):
        """Друзья, подписчики, баланс и залежавшиеся объявления.

        Одним вычислением на четыре поля: все они нужны одной и той же
        странице и в одну и ту же минуту, а раздельно это четыре обхода
        по тем же записям.
        """
        me = self.env.user.partner_id
        wallet = self.env['coop.wallet'].sudo()

        links = self.env['coop.friendship'].sudo().search([
            '|', ('requester_id', 'in', self.ids),
            ('addressee_id', 'in', self.ids),
            ('state', '=', 'accepted'),
        ])
        friends = {}
        for link in links:
            if link.requester_id.id in self.ids:
                friends.setdefault(link.requester_id.id, []).append(
                    link.addressee_id.id)
            if link.addressee_id.id in self.ids:
                friends.setdefault(link.addressee_id.id, []).append(
                    link.requester_id.id)

        # Подписчики — те, кто следит за карточкой. Своя модель подписки
        # не нужна: у Odoo для этого есть подписчики записи, и «написать
        # участнику» уже ходит через них.
        followers = {}
        groups = self.env['mail.followers'].sudo()._read_group(
            [('res_model', '=', 'res.partner'), ('res_id', 'in', self.ids)],
            ['res_id'], ['__count'])
        for res_id, count in groups:
            followers[res_id] = count

        stale_before = fields.Datetime.subtract(
            fields.Datetime.now(), days=STALE_LISTING_DAYS)

        for record in self:
            record.coop_friend_ids = [(6, 0, friends.get(record.id, []))]
            record.coop_follower_count = followers.get(record.id, 0)
            # Баланс и залежавшиеся объявления — только себе. Остаток
            # чужих денег постороннему не показывают, а чужие черновики
            # и залежи — это внутренняя кухня участника.
            own = record.id == me.id
            purse = wallet.search([('partner_id', '=', record.id)], limit=1)                 if own else wallet.browse()
            # Рублёвый остаток, а не крипта и не кредитные линии: в
            # макете в строке показателей стоит одно число в рублях, а
            # разложение по вкладкам — это уже кошелёк.
            record.coop_balance = purse.fiat_balance if purse else 0.0
            record.coop_balance_currency_id = (
                purse.currency_id.id if purse else
                self.env.company.currency_id.id)
            if own:
                stale = self.env['coop.resource'].sudo().search([
                    ('owner_id', '=', record.id),
                    ('state', '=', 'published'),
                    ('create_date', '<=', stale_before),
                ], order='create_date', limit=1)
                record.coop_stale_resource_ids = [(6, 0, stale.ids)]
            else:
                record.coop_stale_resource_ids = [(6, 0, [])]

    def _coop_count_holdings(self):
        """Восемь счётчиков восемью групповыми запросами, а не сотней.

        `_read_group` в Odoo 19 отдаёт кортежи записей, а не словари.
        """
        me = self.env.user.partner_id
        # Владелец видит и то, чего в каталоге нет; посторонний — только
        # опубликованное. Без этого «Моя страница» врёт владельцу о том,
        # сколько у него всего, ровно на число черновиков.
        published = [('state', '=', 'published')]
        own = self.ids == [me.id]

        def tally(model, field, domain=None):
            result = {}
            groups = self.env[model].sudo()._read_group(
                [(field, 'in', self.ids)] + (domain or []), [field], ['__count'])
            for partner, count in groups:
                result[partner.id] = count
            return result

        counts = {
            'offer': tally('coop.skill.offer', 'partner_id',
                           [] if own else published),
            'resource': tally('coop.resource', 'owner_id',
                              [] if own else published),
            'vacancy': tally('coop.vacancy', 'partner_id',
                             [] if own else published),
            'project': tally('coop.project', 'partner_id'),
            'deal': tally('coop.deal', 'party_a_id'),
        }
        # Сделка двусторонняя: считать только по одной стороне значит
        # показать половине участников ноль сделок при десятке проведённых.
        for partner_id, count in tally('coop.deal', 'party_b_id').items():
            counts['deal'][partner_id] = counts['deal'].get(partner_id, 0) + count

        communities = {}
        member_groups = self.env['coop.community.member'].sudo()._read_group(
            [('partner_id', 'in', self.ids), ('state', '=', 'active')],
            ['partner_id'], ['__count'])
        for partner, count in member_groups:
            communities[partner.id] = count
        counts['community'] = communities

        friends = {}
        links = self.env['coop.friendship'].sudo().search([
            '|',
            ('requester_id', 'in', self.ids),
            ('addressee_id', 'in', self.ids),
            ('state', '=', 'accepted'),
        ])
        for link in links:
            for partner in (link.requester_id, link.addressee_id):
                if partner.id in self.ids:
                    friends[partner.id] = friends.get(partner.id, 0) + 1
        counts['friend'] = friends

        drafts = {}
        if own:
            for model, field in (('coop.skill.offer', 'partner_id'),
                                 ('coop.resource', 'owner_id'),
                                 ('coop.vacancy', 'partner_id')):
                for partner_id, count in tally(
                        model, field, [('state', '!=', 'published')]).items():
                    drafts[partner_id] = drafts.get(partner_id, 0) + count
        counts['draft'] = drafts
        return counts

    # ── Переходы к владениям ────────────────────────────────────────────
    #
    # Каждая статкнопка открывает соответствующий каталог, отфильтрованный
    # по владельцу, а не встроенный список. Так человек попадает в тот же
    # экран, что и из бокового меню, с теми же фильтрами и порядком —
    # иначе на платформе оказывается два разных списка ресурсов.

    def _coop_holdings_action(self, xml_id, domain, name):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(xml_id)
        action['domain'] = domain
        action['name'] = name
        context = dict(action.get('context') or {})
        context.pop('search_default_published', None)
        action['context'] = context
        return action

    def action_coop_my_offers(self):
        return self._coop_holdings_action(
            'coop_skills.action_coop_skills',
            [('partner_id', '=', self.id)], _('Навыки — %s') % self.display_name)

    def action_coop_my_resources(self):
        return self._coop_holdings_action(
            'coop_resources.action_coop_resources',
            [('owner_id', '=', self.id)], _('Ресурсы — %s') % self.display_name)

    def action_coop_my_vacancies(self):
        return self._coop_holdings_action(
            'coop_vacancies.action_coop_vacancies',
            [('partner_id', '=', self.id)], _('Вакансии — %s') % self.display_name)

    def action_coop_my_projects(self):
        return self._coop_holdings_action(
            'coop_projects.action_coop_projects',
            [('partner_id', '=', self.id)], _('Проекты — %s') % self.display_name)

    def action_coop_my_communities(self):
        return self._coop_holdings_action(
            'coop_communities.action_coop_communities',
            [('member_ids', 'any', [('partner_id', '=', self.id),
                                    ('state', '=', 'active')])],
            _('Сообщества — %s') % self.display_name)

    def action_coop_my_deals(self):
        return self._coop_holdings_action(
            'coop_deals.action_coop_deals',
            ['|', ('party_a_id', '=', self.id), ('party_b_id', '=', self.id)],
            _('Сделки — %s') % self.display_name)

    def action_coop_my_wallet(self):
        """«История операций» ведёт в тот же кошелёк, что и меню.

        Своего экрана истории здесь нет намеренно: он уже есть в разделе
        кошелька, и второй разошёлся бы с первым на первой же правке.
        """
        self.ensure_one()
        return self.env['ir.actions.actions']._for_xml_id(
            'coop_wallet.action_coop_my_wallet')

    def action_coop_my_needs(self):
        return self._coop_holdings_action(
            'coop_resources.action_coop_resources',
            [('owner_id', '=', self.id), ('listing_type', '=', 'request')],
            _('Потребности — %s') % self.display_name)

    def action_coop_my_friends(self):
        self.ensure_one()
        return self._coop_holdings_action(
            'coop_people.action_coop_people',
            [('id', 'in', self.coop_friend_ids.ids)],
            _('Друзья — %s') % self.display_name)

    # ── Залежавшееся объявление ─────────────────────────────────────────
    #
    # Подтверждение не переписывает объявление, а сдвигает отметку
    # свежести: в каталоге свежие стоят выше, и человек подтверждением
    # возвращает объявлению место в выдаче. Если бы это просто убирало
    # напоминание, подтверждать было бы незачем.

    def action_coop_confirm_listing(self):
        self.ensure_one()
        listing = self.coop_stale_resource_ids[:1]
        if not listing:
            return False
        listing.sudo().write({'refreshed_on': fields.Datetime.now()})
        listing.sudo().message_post(
            body=_('Владелец подтвердил, что объявление актуально.'))
        return {'type': 'ir.actions.act_window_close'}

    def action_coop_unpublish_listing(self):
        self.ensure_one()
        listing = self.coop_stale_resource_ids[:1]
        if not listing:
            return False
        listing.sudo().write({'state': 'archived'})
        return {'type': 'ir.actions.act_window_close'}

    def action_coop_my_listings(self):
        """«Мои объявления» — то, чего в каталоге не видно.

        Не отдельная сущность, а фильтр «мои неопубликованные» по трём
        каталогам. Открывается тот из них, где такие записи есть.
        """
        self.ensure_one()
        for model, xml_id, field, name in (
                ('coop.resource', 'coop_resources.action_coop_resources',
                 'owner_id', _('Мои ресурсы')),
                ('coop.skill.offer', 'coop_skills.action_coop_skills',
                 'partner_id', _('Мои навыки')),
                ('coop.vacancy', 'coop_vacancies.action_coop_vacancies',
                 'partner_id', _('Мои вакансии'))):
            if self.env[model].sudo().search_count(
                    [(field, '=', self.id), ('state', '!=', 'published')]):
                return self._coop_holdings_action(
                    xml_id, [(field, '=', self.id), ('state', '!=', 'published')],
                    name)
        return self.action_coop_my_resources()


    @api.model
    def action_coop_open_my_page(self):
        """«Моя страница» — своя карточка, а не список людей.

        Метод живёт на самом контакте, а не на служебной модели оболочки:
        та абстрактная, прав на неё нет, и серверное действие на ней
        падало у всех, кроме администратора, с «Ошибка доступа».
        """
        # От чьего имени человек действует, от того и страница: переключив
        # себя на организацию, он должен увидеть её владения, а не свои.
        partner = self.env.user._coop_acting_partner()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Моя страница'),
            'res_model': 'res.partner',
            'res_id': partner.id,
            'view_mode': 'form',
            'views': [(self.env.ref('coop_profile.view_coop_profile_form').id,
                       'form')],
            'target': 'current',
            'context': {'coop_my_page': True},
        }
