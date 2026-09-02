# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    """Действие от имени организации.

    Организация на платформе — сторона обязательства, но кнопку всегда
    нажимает человек: учётная запись бывает только у людей, и по-другому
    в движке не бывает. Отсюда две разные ссылки у всего, что публикуется:

    - **владелец** — от чьего имени размещено. Это организация, она и
      отвечает по обязательству перед второй стороной;
    - **автор** — кто из людей это сделал. Он отвечает внутри
      организации, и без этой ссылки спор «кто это разместил» разбирать
      нечем.

    Переключатель хранится на сервере, а не в браузере. Причина не в
    удобстве: при разборе спора надо восстановить, от чьего имени была
    нажата кнопка, а не поверить тому, что осталось в чужом хранилище
    браузера.
    """
    _inherit = 'res.users'

    coop_acting_as_id = fields.Many2one(
        'res.partner', string='Действую от имени',
        help='Пусто — действую от себя. Организация здесь появляется, '
             'только если вы в ней состоите.')

    # Три разных списка, а не один. Одним не обойтись: бухгалтеру нужен
    # доступ к счетам организации и не нужен к публикациям, у сотрудника
    # отдела маркетинга — наоборот. Пока список был один, оба получали всё.
    coop_actor_partner_ids = fields.Many2many(
        'res.partner', string='От чьего имени можно действовать',
        compute='_compute_coop_partner_ids',
        help='Свой профиль и организации, где есть хоть одно полномочие, '
             'которым что-то делают от их имени.')
    coop_publisher_partner_ids = fields.Many2many(
        'res.partner', string='За кого можно публиковать',
        compute='_compute_coop_partner_ids',
        help='Свой профиль и организации с полномочием публикации.')
    coop_treasury_partner_ids = fields.Many2many(
        'res.partner', string='Чьими счетами можно распоряжаться',
        compute='_compute_coop_partner_ids',
        help='Свой профиль и организации с полномочием на счета.')

    # Полномочия, при которых человек вообще действует от имени
    # организации: он что-то создаёт или меняет от её лица. «Переписка» в
    # этот набор не входит — писать от имени организации можно, не владея
    # ни одной её записью.
    ACTING_POWERS = ('publish', 'deal', 'treasury', 'site')

    @api.depends('partner_id')
    def _compute_coop_partner_ids(self):
        """Свой профиль плюс организации — по полномочиям в членстве.

        Под sudo: состав членства читать вправе не каждый, а знать, от
        чьего имени он может действовать, должен любой.

        Ревизионная комиссия сюда не попадает сама собой: исполнительных
        полномочий ей не выдают, а без них организация в список не
        попадает. Отдельной проверки на роль больше нет — она подменяла бы
        собой полномочия и расходилась бы с ними при первой же правке.
        """
        Membership = self.env['coop.membership'].sudo()
        for user in self:
            partner = user.partner_id
            memberships = Membership.search([
                ('partner_id', '=', partner.id),
                ('state', '=', 'active'),
            ])
            acting = self.env['res.partner']
            publishers = self.env['res.partner']
            treasury = self.env['res.partner']
            for membership in memberships:
                codes = set(membership.power_ids.mapped('code'))
                if codes & set(self.ACTING_POWERS):
                    acting |= membership.organization_id
                if 'publish' in codes:
                    publishers |= membership.organization_id
                if 'treasury' in codes:
                    treasury |= membership.organization_id
            user.coop_actor_partner_ids = partner | acting
            user.coop_publisher_partner_ids = partner | publishers
            user.coop_treasury_partner_ids = partner | treasury

    def coop_has_power(self, code, partner=None):
        """Есть ли у человека полномочие в организации.

        Собственный профиль — всегда да: у себя человек вправе всё, что
        платформа вообще позволяет, и членство для этого не нужно.
        """
        self.ensure_one()
        partner = partner or self._coop_acting_partner()
        if partner == self.partner_id:
            return True
        membership = self.env['coop.membership'].sudo().search([
            ('partner_id', '=', self.partner_id.id),
            ('organization_id', '=', partner.id),
            ('state', '=', 'active'),
        ], limit=1)
        return code in set(membership.power_ids.mapped('code'))

    @api.constrains('coop_acting_as_id')
    def _check_coop_acting_as(self):
        for user in self:
            acting = user.coop_acting_as_id
            if acting and acting not in user.coop_actor_partner_ids:
                raise ValidationError(_(
                    'Действовать от имени «%s» нельзя: в этой организации у '
                    'вас нет ни одного полномочия, которым что-то делают от '
                    'её имени.'
                ) % acting.display_name)

    def _coop_acting_partner(self):
        """От чьего имени человек действует прямо сейчас.

        Этим заменяются умолчания вида `self.env.user.partner_id` во всём,
        что публикуется. Раньше объявление всегда оказывалось личным, даже
        когда его размещал представитель организации.
        """
        self.ensure_one()
        return self.coop_acting_as_id or self.partner_id

    def _coop_manageable_partner_ids(self):
        """Чьи объявления человек вправе править.

        Свои и тех организаций, где у него есть полномочие публикации.
        """
        self.ensure_one()
        return self.coop_publisher_partner_ids.ids

    def action_coop_act_as(self, partner_id=False):
        """Переключиться. Вызывается из шапки, поэтому под sudo.

        Право менять собственное поле у участника есть не на всякой
        установке, а переключаться он должен всегда. Проверка при этом не
        обходится: ограничение на допустимые организации остаётся.
        """
        self.ensure_one()
        self.sudo().coop_acting_as_id = partner_id or False
        return True
