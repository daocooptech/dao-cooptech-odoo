# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError


class CoopCommunity(models.Model):
    """Сообщество — группа вокруг соседства, ремесла или общего дела.

    Своя модель, а не канал Discuss с полями. У канала нет города, типа,
    правила вступления, обложки и связи с проектом: каталог из каналов
    не собрать. Обратное — свой чат вместо канала — тоже отпадает,
    писать мессенджер заново незачем. Отсюда пара: карточка наша, канал
    штатный.
    """

    _name = 'coop.community'
    _description = 'Сообщество'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    # Крупные сообщества выше: в каталоге без сортировки первым идёт
    # последнее заведённое, а это чаще всего пустая новая группа.
    _order = 'member_count desc, id desc'

    name = fields.Char(string='Название', required=True, index=True, tracking=True)
    summary = fields.Char(
        string='Кратко',
        help='Одна строка для карточки каталога — чем сообщество занято.')
    description = fields.Html(string='Описание')
    rules = fields.Text(
        string='Правила',
        help='То, с чем человек соглашается, подавая заявку. Пусто — '
             'значит правил нет, и требовать их соблюдения не выйдет.')

    kind = fields.Selection([
        ('neighbourhood', 'Соседское'),
        ('interest', 'По интересам'),
        ('professional', 'Профессиональное'),
        ('financial', 'Финансовое'),
        ('local', 'Локальное'),
    ], string='Тип', required=True, default='interest', index=True, tracking=True)

    city = fields.Char(string='Город', index=True)
    image_1920 = fields.Image(string='Обложка', max_width=1920, max_height=1920)
    image_512 = fields.Image(
        string='Обложка 512', related='image_1920', max_width=512,
        max_height=512, store=True)
    # Значок остаётся для мест, где фотография не нужна и не влезает:
    # строка ленты, строка участника, чип в фильтре.
    icon = fields.Char(string='Значок', size=8)

    # Порог входа и состояние — разные вещи. Замороженное сообщество
    # остаётся открытым по доступу, но писать в него нельзя; одна
    # Selection на оба смысла не даст заморозить закрытое.
    access = fields.Selection([
        ('public', 'Открытое'),
        ('request', 'По заявке'),
        ('closed', 'Закрытое'),
    ], string='Кто может вступить', required=True, default='public',
        index=True, tracking=True,
        help='Открытое — вступают сами. По заявке — решает модератор. '
             'Закрытое — карточка видна всем, состав и обсуждение только '
             'участникам.')

    state = fields.Selection([
        ('draft', 'Черновик'),
        ('published', 'Открыто'),
        ('frozen', 'Заморожено'),
        ('archived', 'Закрыто'),
    ], string='Состояние', required=True, default='draft', index=True,
        tracking=True,
        help='Закрытое сообщество не удаляется и не архивируется '
             'штатно: оно должно остаться в истории тех, кто в нём '
             'состоял.')

    partner_id = fields.Many2one(
        'res.partner', string='Владелец', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(),
        help='От чьего имени сообщество заведено — человека или организации.')
    author_id = fields.Many2one(
        'res.users', string='Создал', readonly=True,
        default=lambda self: self.env.user)

    channel_id = fields.Many2one(
        'discuss.channel', string='Канал обсуждения', ondelete='restrict',
        copy=False, readonly=True)

    # Связь именная и единственная: в макете она читается строкой
    # «связана с проектом …» либо «сообщество кооператива …». Reference
    # не годится — по нему не построить домен правила доступа, а
    # правление организации должно модерировать её сообщество.
    project_id = fields.Many2one(
        'coop.project', string='Проект', ondelete='set null', index=True)
    organization_id = fields.Many2one(
        'res.partner', string='Организация', ondelete='set null', index=True,
        domain=[('is_company', '=', True)])

    member_ids = fields.One2many(
        'coop.community.member', 'community_id', string='Состав')
    # Хранимый: в каталоге две сотни карточек со счётчиком, и len() по
    # связи вытянул бы все строки участия разом.
    member_count = fields.Integer(
        string='Участников', compute='_compute_member_count', store=True,
        index=True)

    coop_member_state = fields.Selection([
        ('none', 'Не участник'),
        ('pending', 'Заявка на рассмотрении'),
        ('active', 'Участник'),
        ('moderator', 'Модератор'),
        ('rejected', 'Заявку отклонили'),
        ('banned', 'Исключён'),
    ], string='Моё участие', compute='_compute_my_relations')
    coop_is_subscribed = fields.Boolean(
        string='Новости приходят', compute='_compute_my_relations')

    import_key = fields.Char(string='Ключ источника', index=True, copy=False)

    _sql_constraints = [
        ('import_key_uniq', 'unique(import_key)',
         'Такой ключ источника уже занят другим сообществом.'),
    ]

    # ── Вычисления ──────────────────────────────────────────────────────

    @api.depends('member_ids.state')
    def _compute_member_count(self):
        counts = {}
        if self.ids:
            groups = self.env['coop.community.member']._read_group(
                [('community_id', 'in', self.ids), ('state', '=', 'active')],
                ['community_id'], ['__count'])
            # В Odoo 19 _read_group отдаёт кортежи записей, а не словари.
            counts = {community.id: count for community, count in groups}
        for record in self:
            record.member_count = counts.get(record.id, 0)

    def _compute_my_relations(self):
        """Отношение текущего пользователя ко всем карточкам сразу.

        Наивный вариант дал бы по два запроса на карточку — при двух
        сотнях плиток это четыреста запросов на открытие каталога.
        """
        partner = self.env.user.partner_id
        mine = {}
        followed = set()
        if self.ids:
            for member in self.env['coop.community.member'].sudo().search([
                    ('community_id', 'in', self.ids),
                    ('partner_id', '=', partner.id)]):
                mine[member.community_id.id] = member
            followed = set(self.env['mail.followers'].sudo().search([
                ('res_model', '=', 'coop.community'),
                ('res_id', 'in', self.ids),
                ('partner_id', '=', partner.id)]).mapped('res_id'))
        for record in self:
            member = mine.get(record.id)
            if not member or member.state == 'left':
                record.coop_member_state = 'none'
            elif member.state == 'active' and member.role != 'member':
                record.coop_member_state = 'moderator'
            else:
                record.coop_member_state = member.state
            record.coop_is_subscribed = record.id in followed

    # ── Проверки ────────────────────────────────────────────────────────

    @api.constrains('project_id', 'organization_id')
    def _check_single_link(self):
        for record in self:
            if record.project_id and record.organization_id:
                raise ValidationError(_(
                    'Сообщество «%s» связано и с проектом, и с '
                    'организацией. Связь одна: две сразу — это два разных '
                    'сообщества.') % record.name)

    @api.constrains('state', 'member_ids')
    def _check_has_owner(self):
        """У опубликованного сообщества должен быть кто-то за него отвечающий.

        Без этого через полгода в каталоге заводятся бесхозные группы,
        которые некому ни модерировать, ни закрыть.
        """
        for record in self:
            if record.state != 'published':
                continue
            owners = record.member_ids.filtered(
                lambda m: m.state == 'active' and m.role == 'owner')
            if not owners:
                raise ValidationError(_(
                    'У сообщества «%s» нет ведущего. Опубликовать группу, '
                    'за которую никто не отвечает, нельзя.') % record.name)

    # ── Действия ────────────────────────────────────────────────────────

    def action_publish(self):
        """Открыть сообщество.

        Порог — подтверждённый контакт (решение владельца 201): группа не
        обязательство и не деньги, а со спамом разбирается модерация.
        Канал заводится здесь, а не при создании: черновики каналов
        никто не откроет, а ленивое создание при первом сообщении даёт
        два канала на двух одновременных постах.
        """
        for record in self:
            record.partner_id.coop_require_level('contact', _('открыть сообщество'))
            if not record.member_ids.filtered(
                    lambda m: m.state == 'active' and m.role == 'owner'):
                record._make_member(record.partner_id, role='owner')
            if not record.channel_id:
                record.channel_id = record.sudo()._create_channel()
            record.state = 'published'
            record.member_ids._sync_channel()
        return True

    def action_freeze(self):
        for record in self:
            record.state = 'frozen'
        return True

    def action_archive_community(self):
        """Закрыть сообщество, не стирая его.

        Штатное архивирование (active=False) убрало бы карточку и из
        каталога, и из истории тех, кто в ней состоял.
        """
        for record in self:
            record.state = 'archived'
        return True

    def action_join(self):
        """Вступить или подать заявку — смотря какое сообщество."""
        self.ensure_one()
        partner = self.env.user.partner_id
        partner.coop_require_level('contact', _('вступить в сообщество'))
        if self.state != 'published':
            raise UserError(_(
                'Сообщество «%s» сейчас не принимает участников.') % self.name)

        existing = self.sudo().member_ids.filtered(
            lambda m: m.partner_id == partner)
        if existing.filtered(lambda m: m.state == 'banned'):
            raise UserError(_(
                'Вас исключили из сообщества «%s». Вступить снова может '
                'только модератор.') % self.name)
        open_member = existing.filtered(lambda m: m.state in ('pending', 'active'))
        if open_member:
            return True

        state = 'active' if self.access == 'public' else 'pending'
        member = self._make_member(partner, state=state)
        # Подписка включается вместе с вступлением: почти всем она нужна,
        # а выключить её отдельным действием можно в любой момент.
        self.message_subscribe(partner_ids=partner.ids)
        return member

    def action_leave(self):
        self.ensure_one()
        partner = self.env.user.partner_id
        member = self.sudo().member_ids.filtered(
            lambda m: m.partner_id == partner and m.state in ('pending', 'active'))
        if not member:
            return True
        member.write({'state': 'left', 'left_on': fields.Date.context_today(self)})
        return True

    def action_toggle_subscription(self):
        """Показывать новости в ленте или не показывать.

        Не связано с участием (решение владельца 200): читать, не
        вступая, можно — и состоять, не читая, тоже.
        """
        self.ensure_one()
        partner = self.env.user.partner_id
        if partner in self.message_partner_ids:
            self.message_unsubscribe(partner_ids=partner.ids)
        else:
            self.message_subscribe(partner_ids=partner.ids)
        return True

    def action_open_applications(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Заявки в «%s»') % self.name,
            'res_model': 'coop.community.member',
            'view_mode': 'list,form',
            'domain': [('community_id', '=', self.id), ('state', '=', 'pending')],
            'context': {'default_community_id': self.id},
        }

    def action_resync_channel(self):
        """Свести состав канала с составом сообщества.

        Руками, а не по расписанию: молчаливая починка вернула бы в канал
        того, кто из него сознательно вышел.
        """
        for record in self:
            record.member_ids._sync_channel()
        return True

    # ── Внутреннее ──────────────────────────────────────────────────────

    def _make_member(self, partner, role='member', state='active'):
        self.ensure_one()
        values = {
            'community_id': self.id,
            'partner_id': partner.id,
            'role': role,
            'state': state,
        }
        if state == 'pending':
            values['applied_on'] = fields.Datetime.now()
        else:
            values['joined_on'] = fields.Date.context_today(self)
        return self.env['coop.community.member'].sudo().create(values)

    def _create_channel(self):
        """Завести канал под сообщество.

        Приватность выражается типом канала, а не своей группой доступа:
        группа на каждое сообщество попала бы в набор групп каждого
        пользователя и замедлила проверки прав на всей платформе.
        """
        self.ensure_one()
        values = {
            'name': self.name,
            'description': self.summary or '',
        }
        if self.access == 'closed':
            values['channel_type'] = 'group'
        else:
            values['channel_type'] = 'channel'
            values['group_public_id'] = self.env.ref('base.group_user').id
        return self.env['discuss.channel'].create(values)


class CoopCommunityMember(models.Model):
    """Участие в сообществе — оно же заявка, оно же роль.

    Заявка не отдельная модель: поля те же (кто, куда, когда), а
    отдельная таблица немедленно требует «одобрил заявку → создай
    участие → не забудь пометить заявку» и двух расходящихся источников
    истины. Так же устроено членство в организации.
    """

    _name = 'coop.community.member'
    _description = 'Участие в сообществе'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    community_id = fields.Many2one(
        'coop.community', string='Сообщество', required=True, index=True,
        ondelete='cascade')
    partner_id = fields.Many2one(
        'res.partner', string='Участник', required=True, index=True,
        ondelete='cascade')

    # Роль полем, а не группой доступа: две сотни сообществ дали бы две
    # сотни групп в наборе каждого пользователя.
    role = fields.Selection([
        ('member', 'Участник'),
        ('moderator', 'Модератор'),
        ('owner', 'Ведущий'),
    ], string='Роль', required=True, default='member', index=True, tracking=True)

    state = fields.Selection([
        ('pending', 'Заявка подана'),
        ('active', 'Участник'),
        ('left', 'Вышел'),
        ('rejected', 'Заявку отклонили'),
        ('banned', 'Исключён'),
    ], string='Состояние', required=True, default='active', index=True,
        tracking=True)

    applied_on = fields.Datetime(string='Заявка подана', readonly=True)
    application_note = fields.Text(string='Что написал в заявке')
    decided_by_id = fields.Many2one('res.users', string='Кто решил', readonly=True)
    decided_on = fields.Datetime(string='Когда решено', readonly=True)
    decision_reason = fields.Char(
        string='Основание решения',
        help='Молчаливый отказ — худшее, что может случиться с новичком.')

    joined_on = fields.Date(string='Вступил', tracking=True)
    left_on = fields.Date(string='Вышел', tracking=True)

    city = fields.Char(related='partner_id.city', string='Город', store=False)

    def _auto_init(self):
        """Одно незакрытое участие на пару «человек — сообщество».

        Частичный индекс, а не unique(community_id, partner_id): вышедший
        должен иметь возможность вернуться, а запись о прошлом выходе —
        остаться.
        """
        result = super()._auto_init()
        tools.create_index(
            self.env.cr, 'coop_community_member_open_uniq', self._table,
            ['community_id', 'partner_id'], unique=True,
            where="state IN ('pending', 'active')")
        return result

    @api.constrains('state', 'community_id', 'partner_id')
    def _check_single_open_membership(self):
        """То же, что индекс, но словами — индекс ловит гонку, а это объясняет."""
        for record in self:
            if record.state not in ('pending', 'active'):
                continue
            twin = self.sudo().search_count([
                ('id', '!=', record.id),
                ('community_id', '=', record.community_id.id),
                ('partner_id', '=', record.partner_id.id),
                ('state', 'in', ('pending', 'active')),
            ])
            if twin:
                raise ValidationError(_(
                    '%s уже состоит в сообществе «%s» или подал заявку. '
                    'Второй записи об участии не нужно.')
                    % (record.partner_id.display_name,
                       record.community_id.name))

    @api.constrains('state', 'role', 'community_id')
    def _check_community_keeps_owner(self):
        """Последний ведущий не может уйти, не передав сообщество.

        Проверка живёт здесь, а не только на самом сообществе: правило
        на карточке срабатывает, когда пишут в неё, а выход участника
        меняет его собственную запись — карточка при этом не
        затрагивается, и опубликованная группа оставалась без
        ответственного.
        """
        for community in self.community_id:
            if community.state != 'published':
                continue
            owners = community.sudo().member_ids.filtered(
                lambda m: m.state == 'active' and m.role == 'owner')
            if not owners:
                raise ValidationError(_(
                    'В сообществе «%s» не останется ведущего. Сначала '
                    'назначьте ведущим кого-то из участников, потом '
                    'выходите: группа без ответственного — это группа, '
                    'которую некому ни модерировать, ни закрыть.')
                    % community.name)

    def unlink(self):
        """Удаление записи об участии тоже не должно осиротить сообщество."""
        communities = self.community_id
        result = super().unlink()
        for community in communities.exists():
            if community.state != 'published':
                continue
            owners = community.sudo().member_ids.filtered(
                lambda m: m.state == 'active' and m.role == 'owner')
            if not owners:
                raise ValidationError(_(
                    'В сообществе «%s» не останется ведущего.') % community.name)
        return result

    # ── Действия модератора ─────────────────────────────────────────────

    def action_admit(self):
        for record in self:
            record.write({
                'state': 'active',
                'joined_on': fields.Date.context_today(record),
                'decided_by_id': self.env.user.id,
                'decided_on': fields.Datetime.now(),
            })
        return True

    def action_reject(self):
        for record in self:
            if not record.decision_reason:
                raise UserError(_(
                    'Укажите, почему заявка отклонена. Отказ без причины '
                    'человек прочитать не может, а подать заявку снова — '
                    'может, и по кругу.'))
            record.write({
                'state': 'rejected',
                'decided_by_id': self.env.user.id,
                'decided_on': fields.Datetime.now(),
            })
        return True

    def action_ban(self):
        """Исключить.

        Сообщения исключённого остаются в канале (решение владельца 202):
        исключение отбирает доступ, а не текст.
        """
        for record in self:
            if not record.decision_reason:
                raise UserError(_(
                    'Укажите основание исключения. Без него ни участник, '
                    'ни следующий модератор не поймут, что произошло.'))
            record.write({
                'state': 'banned',
                'left_on': fields.Date.context_today(record),
                'decided_by_id': self.env.user.id,
                'decided_on': fields.Datetime.now(),
            })
        return True

    # ── Канал ───────────────────────────────────────────────────────────

    def _sync_channel(self):
        """Состав канала — следствие состава сообщества, не наоборот.

        Обратной синхронизации нет намеренно: кнопка «покинуть» в
        мессенджере нажимается случайно, а у участия есть последствия
        помимо чтения переписки.
        """
        for record in self:
            channel = record.community_id.channel_id.sudo()
            if not channel:
                continue
            partner = record.partner_id
            inside = partner in channel.channel_member_ids.partner_id
            if record.state == 'active' and not inside:
                channel._add_members(partners=partner, post_joined_message=False)
            elif record.state != 'active' and inside:
                channel._action_unfollow(partner=partner, post_leave_message=False)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_channel()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'state', 'partner_id'} & set(vals):
            self._sync_channel()
        return result
