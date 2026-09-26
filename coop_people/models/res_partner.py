# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _plural(n, one, few, many):
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    return one if n == 1 else few if 2 <= n <= 4 else many


class ResPartner(models.Model):
    """Человек как участник платформы.

    В Odoo `res.partner` — это «с кем мы имеем дело»: и покупатель, и
    поставщик, и сотрудник, и организация. Каталог людей платформы — не то
    же самое: там участники, у которых есть навыки, город, уровень доверия
    и возможность написать друг другу напрямую.

    Поэтому не новая модель, а признак и несколько полей: заводить второго
    человека рядом с контактом значит получить два справочника людей,
    которые немедленно разъедутся.
    """
    _inherit = 'res.partner'

    coop_birthdate = fields.Date(string='Дата рождения')
    coop_age = fields.Integer(string='Возраст', compute='_compute_age')

    coop_skill_ids = fields.Many2many(
        'hr.skill', 'coop_partner_skill_rel', 'partner_id', 'skill_id',
        string='Навыки',
        help='Что человек умеет делать. Навык здесь — не должность и не '
             'образование, а работа, которую он готов взять.')

    # Проверка личности — отдельная вещь от доверия, и в макете это
    # оговорено подсказкой. Смешивать их нельзя: подтверждённый паспорт
    # ничего не говорит о том, как человек исполняет обязательства.
    # Ступеней теперь четыре, и булево стало их следствием, а не
    # источником: оно осталось затем, что на него смотрят представления и
    # фильтры каталога, и переписывать их разом незачем.
    coop_verified = fields.Boolean(
        string='Личность подтверждена',
        compute='_compute_coop_verified', store=True, readonly=True,
        help='Ступень «Личность подтверждена» или выше. На уровень доверия '
             'не влияет: это разные вещи. Проверка личности говорит, кто '
             'человек, доверие — как он исполняет обязательства.')

    @api.depends('coop_verification_level')
    def _compute_coop_verified(self):
        for partner in self:
            partner.coop_verified = partner.coop_verification_level == 'identity'

    coop_membership_ids = fields.One2many(
        'coop.membership', 'partner_id', string='Членство')
    # Хранимое: по нему фильтруют в каталоге, а по вычисляемому на лету
    # искать нельзя — Odoo не умеет переводить такое в запрос к базе.
    coop_membership_count = fields.Integer(
        string='Кооперативов', compute='_compute_membership_count', store=True)

    # Карточка каталога людей (решение 411, Н1): «каждому добавить
    # специализации, которые они себе проставляют в настройках, и после
    # уровня доверия — количество сделок». Строкой, а не чипами: чипы на
    # плитке уже заняты навыками, и два ряда чипов подряд не различить.
    coop_specialization_label = fields.Char(
        string='Специализации', compute='_compute_card_labels')
    coop_deals_label = fields.Char(
        string='Сделок', compute='_compute_card_labels')

    @api.depends('coop_specialization_id', 'coop_specialization_ids', 'coop_deals_done')
    def _compute_card_labels(self):
        for partner in self:
            # Главная — первой: по ней человек подписан и отсортирован.
            specs = partner.coop_specialization_id | partner.coop_specialization_ids
            partner.coop_specialization_label = ' · '.join(specs.mapped('name'))
            count = partner.coop_deals_done or 0
            partner.coop_deals_label = '%s %s' % (count, _plural(count, 'сделка', 'сделки', 'сделок'))                 if count else ''

    @api.depends('coop_birthdate')
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for record in self:
            if record.coop_birthdate:
                record.coop_age = relativedelta(today, record.coop_birthdate).years
            else:
                record.coop_age = 0

    # Действующие членства, по одному на организацию.
    #
    # Полка «Организации» на своей странице рисовалась по всем членствам с
    # доменом «действующее» — а домен у поля в карточке отбирает то, что
    # можно выбрать, а не то, что показано. На боевом это дало сорок
    # девять плиток вместо четырнадцати: тридцать два прекращённых
    # членства, два заявления и одна организация четырежды — человек
    # уходил и возвращался.
    coop_active_membership_ids = fields.Many2many(
        'coop.membership', string='Действующее членство',
        compute='_compute_active_memberships')

    @api.depends('coop_membership_ids.state', 'coop_membership_ids.organization_id')
    def _compute_active_memberships(self):
        for record in self:
            seen = set()
            picked_list = record.coop_membership_ids.browse()
            for membership in record.coop_membership_ids.filtered(
                    lambda m: m.state == 'active'):
                if membership.organization_id.id in seen:
                    continue
                seen.add(membership.organization_id.id)
                picked_list |= membership
            record.coop_active_membership_ids = picked_list

    @api.depends('coop_membership_ids.state')
    def _compute_membership_count(self):
        for record in self:
            record.coop_membership_count = len(
                record.coop_membership_ids.filtered(lambda m: m.state == 'active'))

    # ── Подписка и дружба ────────────────────────────────────────────────
    #
    # Оба поля считаются относительно текущего пользователя, поэтому они
    # не хранимые: одна и та же запись выглядит по-разному для разных
    # людей, и хранить тут нечего. Искать по ним нельзя — и не нужно:
    # «мои друзья» ищутся по самой связи, а не по признаку у контакта.
    coop_is_following = fields.Boolean(
        string='Я подписан', compute='_compute_coop_relations')
    coop_friend_state = fields.Selection(
        [('none', 'Не в друзьях'),
         ('pending_out', 'Предложение отправлено'),
         ('pending_in', 'Ждёт вашего ответа'),
         ('accepted', 'В друзьях')],
        string='Дружба', compute='_compute_coop_relations')
    coop_is_self = fields.Boolean(
        string='Это я', compute='_compute_coop_relations',
        help='Свою карточку в каталоге видно, но кнопки действий на ней '
             'бессмысленны и потому скрыты.')

    def _compute_coop_relations(self):
        me = self.env.user.partner_id
        links = self.env['coop.friendship'].search([
            '|',
            '&', ('requester_id', '=', me.id), ('addressee_id', 'in', self.ids),
            '&', ('addressee_id', '=', me.id), ('requester_id', 'in', self.ids),
        ])
        by_partner = {}
        for link in links:
            other = link.addressee_id if link.requester_id == me else link.requester_id
            outgoing = link.requester_id == me
            if link.state == 'accepted':
                by_partner[other.id] = 'accepted'
            elif link.state == 'pending':
                by_partner[other.id] = 'pending_out' if outgoing else 'pending_in'
        for record in self:
            record.coop_is_self = record == me
            record.coop_is_following = me in record.message_partner_ids
            record.coop_friend_state = by_partner.get(record.id, 'none')

    def action_coop_follow(self):
        """Подписаться на человека или отписаться.

        Одна кнопка на оба действия: подписка — состояние, а не событие,
        и отдельная кнопка «Отписаться» на карточке в каталоге заняла бы
        место ради того, что нужно раз в год.
        """
        self.ensure_one()
        me = self.env.user.partner_id
        if me in self.message_partner_ids:
            self.message_unsubscribe(partner_ids=me.ids)
        else:
            self.message_subscribe(partner_ids=me.ids)
        return True

    def action_coop_befriend(self):
        """Предложить дружбу или принять встречное предложение.

        Дружба двусторонняя, поэтому нажатие означает разное в разных
        состояниях: если человек уже предложил дружбу нам — нажатие её
        принимает, а не создаёт второе предложение навстречу.
        """
        self.ensure_one()
        me = self.env.user.partner_id
        if self == me:
            raise UserError(_('Нельзя добавить в друзья самого себя.'))
        Friendship = self.env['coop.friendship'].sudo()
        incoming = Friendship.search([
            ('requester_id', '=', self.id), ('addressee_id', '=', me.id),
        ], limit=1)
        if incoming:
            if incoming.state != 'accepted':
                incoming.state = 'accepted'
            return True
        outgoing = Friendship.search([
            ('requester_id', '=', me.id), ('addressee_id', '=', self.id),
        ], limit=1)
        if not outgoing:
            Friendship.create({'requester_id': me.id, 'addressee_id': self.id})
        return True

    def action_coop_message(self):
        """Написать участнику — открыть с ним диалог в разделе «Сообщения».

        Раньше кнопка открывала форму канала движка: всплывало окно
        «Название группы», «Описание», «Группы автоподписки» — то есть
        предложение завести группу вместо разговора с человеком.
        Владелец 20 сентября 2026: «когда я нажимаю написать должна
        открываться страница сообщения и диалог с этим участником».

        Если участник принимает письма не от всех — всплывает уведомление
        и диалог не заводится. Проверка живёт в `coop_base`, чтобы
        отвечать одинаково отовсюду.
        """
        self.ensure_one()
        if not self.coop_can_message_me():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'warning',
                    'title': self.display_name,
                    'message': _('Участник принимает сообщения только от '
                                 'друзей и сторон совместных сделок.'),
                    'sticky': False,
                },
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'coop_messages.messages',
            'name': _('Сообщения'),
            'params': {'coop_partner_id': self.id},
        }


class ResPartnerCatalogFilters(models.Model):
    """Панель фильтров каталога людей — та же, что в макете.

    Порядок полей и подписи взяты из `people.html`: специализация (сфера),
    под ней подкатегория, город, навыки, уровень доверия.

    Модель общая с организациями, и каталог организаций смотрит на ту же
    `res.partner`. Какой каталог спрашивает, видно по основному отбору
    раздела (`coop_base_domain` в контексте): у людей в нём
    `is_company = False`. Организациям панель пока не выставлена — их
    набор полей в макете другой, и без описания лучше честная строка
    «отбирают поиском», чем чужие поля.

    Счётчики у вариантов считаются здесь, а не темой: тема считает по
    всей модели, и в число «Информационные технологии · 40» попадали бы
    организации той же сферы.
    """

    _inherit = 'res.partner'

    # Пороги — из макета: «от 90 %, от 75 %, от 50 %».
    _COOP_TRUST_STEPS = (90, 75, 50)

    def _coop_catalog_filters(self, domain):
        base = list(self.env.context.get('coop_base_domain') or [])
        if ('is_company', '=', False) not in [
                tuple(leaf) for leaf in base
                if isinstance(leaf, (list, tuple)) and len(leaf) == 3]:
            return []

        def without(*fields_):
            # Условия панели, кроме условий на само поле: иначе выбор
            # одной сферы обнулил бы счётчики у остальных, и сменить её
            # было бы не на что.
            return base + [leaf for leaf in domain or []
                           if not (isinstance(leaf, (list, tuple)) and leaf
                                   and leaf[0] in fields_)]

        # Без sudo: считать надо ровно то, что человеку покажет каталог,
        # со всеми правилами видимости.
        people = self

        def counts(field, dom):
            return {(value.id if hasattr(value, 'id') else value): count
                    for value, count in people._read_group(
                        dom, [field], ['__count'])}

        spheres = self.env['coop.specialization.category'].sudo().search(
            [], order='name')
        sphere_counts = counts('coop_specialization_category_ids',
                               without('coop_specialization_category_ids',
                                       'coop_specialization_ids'))
        blocks = [{
            'code': 'sphere', 'label': 'Специализация',
            'hint': 'Профессиональная область, как на hh.ru.',
            'widget': 'select', 'field': 'coop_specialization_category_ids',
            'operator': '=', 'placeholder': 'Любая', 'counted': True,
            # Подкатегории зависят от выбранной сферы — панель
            # перечитывается сразу, как в макете, а не после «Показать».
            'reload': True,
            'options': [{'value': s.id, 'label': s.name,
                         'count': sphere_counts.get(s.id, 0)}
                        for s in spheres],
        }]

        sphere = next((leaf[2] for leaf in domain or []
                       if isinstance(leaf, (list, tuple)) and len(leaf) == 3
                       and leaf[0] == 'coop_specialization_category_ids'), None)
        if sphere:
            specs = self.env['coop.specialization'].sudo().search(
                [('category_id', '=', int(sphere))], order='name')
            spec_counts = counts('coop_specialization_ids',
                                 without('coop_specialization_ids'))
            blocks.append({
                'code': 'specialization', 'label': 'Подкатегория',
                'widget': 'select', 'field': 'coop_specialization_ids',
                'operator': '=', 'placeholder': 'Любая', 'counted': True,
                'options': [{'value': s.id, 'label': s.name,
                             'count': spec_counts.get(s.id, 0)}
                            for s in specs],
            })

        cities = sorted(c for c in counts('city', base) if c)
        blocks.append({
            'code': 'city', 'label': 'Город',
            'hint': 'Показать участников только из выбранного города.',
            'widget': 'text', 'field': 'city', 'operator': 'ilike',
            'placeholder': 'Начните вводить город',
            'options': [{'value': c, 'label': c} for c in cities],
        })

        skill_counts = counts('coop_skill_ids', base)
        skills = self.env['hr.skill'].sudo().browse(
            [k for k in skill_counts if k]).exists().sorted('name')
        blocks.append({
            'code': 'skills', 'label': 'Навыки',
            'hint': 'Можно выбрать несколько — начните вводить название и '
                    'выберите из списка. Покажутся люди с любым из них.',
            'widget': 'tags', 'field': 'coop_skill_ids',
            'placeholder': 'Например, сварка',
            'options': [{'value': s.id, 'label': s.name} for s in skills],
        })

        trust_base = without('coop_trust')
        blocks.append({
            'code': 'trust', 'label': 'Уровень доверия',
            'hint': 'Двусторонние отзывы после сделок, хранятся в блокчейне '
                    'и неизменны.',
            'widget': 'select', 'field': 'coop_trust', 'operator': '>=',
            'number': True, 'placeholder': 'Любой', 'counted': True,
            'options': [{'value': step, 'label': f'От {step}%',
                         'count': people.search_count(
                             trust_base + [('coop_trust', '>=', step)])}
                        for step in self._COOP_TRUST_STEPS],
        })
        return blocks
