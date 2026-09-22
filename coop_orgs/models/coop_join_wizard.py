# -*- coding: utf-8 -*-
"""Заявление о вступлении в организацию.

Модель членства описана до мелочей — основание участия, полномочия,
голос, дата приёма, основание приёма, — а подать заявление участник не
мог: на карточке организации есть «Написать» и «Подписаться», и всё.
Состав заводился только загрузчиком демо-данных и вручную из
администраторского списка.

Проверено 15 сентября 2026: в представлениях `coop_orgs` нет ни одной
кнопки, ведущей к `coop.membership`.

Окном, а не кнопкой сразу: основание участия — не мелочь. Пайщик вносит
пай и получает голос, наёмный сотрудник не получает ни того ни другого,
и человек должен выбрать сам, а не узнать постфактум, кем его записали.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopJoinWizard(models.TransientModel):
    _name = 'coop.org.join'
    _description = 'Заявление о вступлении в организацию'

    organization_id = fields.Many2one(
        'res.partner', string='Организация', required=True, readonly=True)
    is_cooperative = fields.Boolean(
        related='organization_id.coop_is_cooperative', readonly=True)
    # Из семи оснований участия выбрать можно только два. Учредителем
    # становятся при создании, в правление и ревизию выбирает собрание,
    # рабочая группа платформы к кооперативу отношения не имеет — ни одно
    # из этих оснований не возникает по заявлению.
    role_id = fields.Many2one(
        'coop.membership.role', string='Кем вступаете', required=True,
        ondelete='restrict', domain="[('id', 'in', allowed_role_ids)]",
        default=lambda self: self._default_join_role())
    allowed_role_ids = fields.Many2many(
        'coop.membership.role', string='Из чего выбирать',
        compute='_compute_allowed_role_ids')
    # Код выбранной роли — для условий в виде: должность спрашивают у
    # сотрудника, а про пай рассказывают пайщику. Условие вида не умеет
    # заглядывать в `role_id.code`, поэтому код приходит отдельно.
    role_code = fields.Char(related='role_id.code', readonly=True)
    job_title = fields.Char(
        string='Должность',
        help='Как называется место в организации. На права не влияет.')
    note = fields.Text(string='Пара слов о себе')

    # По заявлению возникают только эти два основания. Пайщиком берут
    # в кооператив, сотрудником — куда угодно; а вот учредителем
    # становятся при создании, в правление и ревизию выбирает собрание,
    # и рабочая группа платформы к кооперативу отношения не имеет.
    BY_APPLICATION = ('member', 'staff')

    @api.model
    def _default_join_role(self):
        # Мастер — временная модель, столбцов у неё нет, и беды
        # `coop.membership` с обязательным столбцом тут быть не может.
        # Но справочник может быть ещё не заведён на свежей базе.
        Role = self.env['coop.membership.role']
        return Role.search([('code', '=', 'member')], limit=1)

    @api.depends('organization_id')
    def _compute_allowed_role_ids(self):
        """Из чего выбирать — по правовой форме организации.

        В ООО пайщиком не вступают: паёв там нет. Прежде этот выбор
        предлагался всем одинаково, и человек узнавал о запрете уже
        отказом (решения 180 и 371). Выбор, которого нет, лучше не
        показывать вовсе.
        """
        roles = self.env['coop.membership.role'].search(
            [('code', 'in', self.BY_APPLICATION)])
        for record in self:
            group = record.organization_id.coop_legal_form_group_id
            record.allowed_role_ids = roles.filtered(
                lambda r: r.fits_group(group))

    def action_apply(self):
        self.ensure_one()
        organization = self.organization_id
        me = self.env.user.partner_id
        if not organization.is_company:
            raise UserError(_('Вступают в организацию, а не к человеку.'))
        if organization == me:
            raise UserError(_('Это ваша собственная карточка.'))

        Membership = self.env['coop.membership'].sudo()
        # Открытое членство уже есть — второе завести нельзя, и проверка
        # базы это не пропустит. Говорим об этом словами, а не ошибкой
        # уникального индекса.
        open_one = Membership.search([
            ('partner_id', '=', me.id),
            ('organization_id', '=', organization.id),
            ('state', 'in', ('applied', 'active', 'leaving')),
        ], limit=1)
        if open_one:
            raise UserError(_(
                'У вас уже есть открытое членство в «%(org)s»: %(what)s.',
                org=organization.display_name,
                what=dict(open_one._fields['state'].selection)[open_one.state]))

        membership = Membership.create({
            'partner_id': me.id,
            'organization_id': organization.id,
            'role_id': self.role_id.id,
            'job_title': self.job_title or False,
            'state': 'applied',
            # Пая и голоса до приёма нет: заявление ещё не решение.
            'has_vote': self.role_id.code == 'member',
        })

        body = _('Заявление о вступлении в «%(org)s»: %(who)s, %(by_whom)s.',
                 org=organization.display_name, who=me.display_name,
                 by_whom=self.role_id.name)
        if self.note:
            body = '%s %s' % (body, self.note)
        # Тем, кто вправе принимать, а не всей организации: у кооператива
        # на полторы сотни пайщиков заявление иначе уходит в пустоту.
        self.env['coop.notification']._notify(
            membership._roster_deciders(), body,
            record=organization, kind='org')
        organization.sudo().message_post(body=body)
        return {'type': 'ir.actions.act_window_close'}
