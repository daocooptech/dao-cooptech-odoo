# -*- coding: utf-8 -*-
"""Отклик на объявление о ресурсе.

Каталог ресурсов — самый большой на платформе: без малого тысяча восемьсот
объявлений. Действий у него было три: «Опубликовать», «Закрыть»,
«Продвинуть» — все три владельца объявления. Тому, кто пришёл со стороны
и нашёл нужное, нажать было нечего. Проверено 15 сентября 2026: в
представлениях `coop_resources` нет ни одной кнопки участника.

Отклик заводит сделку в состоянии «Переговоры». Не письмо и не заявку:
сделка на платформе уже есть, она двусторонняя, у неё состояния,
спецификация, сроки, приёмка, спор и отзывы. Заводить рядом вторую
сущность «отклик» значило бы держать две конструкции об одном.

Кто чья сторона. У предложения («отдам, продам, сдам») владелец
объявления передаёт, откликнувшийся принимает. У спроса («ищу, куплю,
приму в дар») — наоборот. Путать нельзя: от стороны зависят роли в
приёмке и кто кому платит.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Способ передачи из объявления — в способ сделки. Наборы разные:
# объявление говорит, как владелец готов расстаться с вещью, сделка —
# как она передаётся на самом деле.
WAY = {
    'sale': 'sale',
    'rent': 'rent',
    'installment': 'sale',
    'leasing': 'rent',
    'barter': 'exchange',
    'free': 'gift',
    'project': 'sale',
}


class CoopResourceRespond(models.TransientModel):
    _name = 'coop.resource.respond'
    _description = 'Отклик на объявление о ресурсе'

    resource_id = fields.Many2one(
        'coop.resource', string='Объявление', required=True, readonly=True)
    listing_type = fields.Selection(
        related='resource_id.listing_type', readonly=True)
    owner_id = fields.Many2one(
        related='resource_id.owner_id', string='Владелец объявления',
        readonly=True)
    currency_id = fields.Many2one(
        related='resource_id.currency_id', readonly=True)
    method_id = fields.Many2one(
        'coop.resource.method', string='Каким образом',
        domain="[('id', 'in', available_method_ids)]",
        help='Из способов, которые владелец указал в объявлении.')
    available_method_ids = fields.Many2many(
        'coop.resource.method', compute='_compute_available_methods')
    amount = fields.Monetary(
        string='Сумма', currency_field='currency_id',
        help='Оценка сделки. Подставлена из объявления — поправьте, если '
             'договариваетесь о другом.')
    note = fields.Text(
        string='Что предлагаете',
        help='Пара слов второй стороне: когда готовы, на каких условиях.')

    @api.depends('resource_id')
    def _compute_available_methods(self):
        for wizard in self:
            wizard.available_method_ids = wizard.resource_id.method_ids

    @api.onchange('resource_id')
    def _onchange_resource(self):
        for wizard in self:
            if wizard.resource_id and not wizard.method_id:
                wizard.method_id = wizard.resource_id.method_ids[:1]

    def action_respond(self):
        self.ensure_one()
        listing = self.resource_id
        me = self.env.user._coop_acting_partner()

        if listing.state != 'published':
            raise UserError(_(
                'Откликаться можно на опубликованное объявление. Это в '
                'состоянии «%s».') % dict(
                    listing._fields['state'].selection)[listing.state])
        if listing.owner_id == me:
            raise UserError(_(
                'Это ваше объявление. Откликаются на чужие.'))

        # Сторону определяет вид объявления, а не кто нажал кнопку.
        if listing.listing_type == 'offer':
            side_a, side_b = listing.owner_id, me
            role_a, role_b = _('Передаёт'), _('Принимает')
        else:
            side_a, side_b = me, listing.owner_id
            role_a, role_b = _('Передаёт'), _('Принимает')

        way = WAY.get(self.method_id.code or '', 'sale')
        # Сделку заводим через sudo: вторая сторона чужая, и права
        # заводить запись, где она стоит стороной, у откликнувшегося нет.
        # Проверки выше — вместо этих прав.
        deal = self.env['coop.deal'].sudo().create({
            'name': listing.name,
            'subject': 'resource',
            'way': way,
            'party_a_id': side_a.id,
            'party_b_id': side_b.id,
            'role_a': role_a,
            'role_b': role_b,
            'author_id': self.env.user.partner_id.id,
            'resource_id': listing.id,
            'city': listing.city or '',
            'amount': self.amount or listing.price or 0.0,
            'state': 'draft',
        })

        body = _('Отклик на объявление «%(что)s» от %(кто)s. '
                 'Заведены переговоры по сделке %(номер)s.',
                 what=listing.name, who=me.display_name,
                 number=deal.number or '')
        if self.note:
            body = '%s %s' % (body, self.note)
        self.env['coop.notification']._notify(
            listing.owner_id, body, record=deal, kind='deal')
        deal.message_post(body=body)

        # Открываем заведённую сделку: договариваются дальше в ней, а не
        # в переписке, и человек должен увидеть, куда его отклик попал.
        return {
            'type': 'ir.actions.act_window',
            'name': _('Сделка %s') % (deal.number or ''),
            'res_model': 'coop.deal',
            'res_id': deal.id,
            'view_mode': 'form',
            'target': 'current',
        }
