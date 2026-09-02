# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


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

    @api.depends('coop_birthdate')
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for record in self:
            if record.coop_birthdate:
                record.coop_age = relativedelta(today, record.coop_birthdate).years
            else:
                record.coop_age = 0

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
        """Написать участнику.

        Открывает переписку, а не форму письма: на платформе договариваются
        в чате, и след договорённости должен остаться там же, где сделка.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'discuss.channel',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_channel_partner_ids': [(4, self.id)]},
            'name': 'Написать: %s' % self.name,
        }
