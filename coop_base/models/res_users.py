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

    coop_actor_partner_ids = fields.Many2many(
        'res.partner', string='От чьего имени можно действовать',
        compute='_compute_coop_actor_partner_ids',
        help='Свой профиль и организации, где есть действующее членство.')

    @api.depends('partner_id')
    def _compute_coop_actor_partner_ids(self):
        """Свой профиль плюс организации с действующим членством.

        Под sudo: состав членства читать вправе не каждый, а знать, от
        чьего имени он может действовать, должен любой.

        Ревизионная комиссия исключена намеренно. Её дело — смотреть и
        проверять; публикация от имени организации ревизором сделала бы
        проверяющего участником того, что он проверяет.
        """
        Membership = self.env['coop.membership'].sudo()
        for user in self:
            partner = user.partner_id
            memberships = Membership.search([
                ('partner_id', '=', partner.id),
                ('state', '=', 'active'),
                ('role', '!=', 'audit'),
            ])
            user.coop_actor_partner_ids = partner | memberships.organization_id

    @api.constrains('coop_acting_as_id')
    def _check_coop_acting_as(self):
        for user in self:
            acting = user.coop_acting_as_id
            if acting and acting not in user.coop_actor_partner_ids:
                raise ValidationError(_(
                    'Действовать от имени «%s» нельзя: у вас нет '
                    'действующего членства в этой организации.'
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
        """Чьи записи человек вправе править.

        Свои и своих организаций. До этого правила владения были написаны
        на личного партнёра, и представитель организации не мог
        отредактировать объявление собственной организации вовсе — это не
        замечалось только потому, что всё проверялось под администратором.
        """
        self.ensure_one()
        return self.coop_actor_partner_ids.ids

    def action_coop_act_as(self, partner_id=False):
        """Переключиться. Вызывается из шапки, поэтому под sudo.

        Право менять собственное поле у участника есть не на всякой
        установке, а переключаться он должен всегда. Проверка при этом не
        обходится: ограничение на допустимые организации остаётся.
        """
        self.ensure_one()
        self.sudo().coop_acting_as_id = partner_id or False
        return True
