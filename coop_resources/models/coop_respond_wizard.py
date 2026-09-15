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
СПОСОБ = {
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
        объявление = self.resource_id
        я = self.env.user._coop_acting_partner()

        if объявление.state != 'published':
            raise UserError(_(
                'Откликаться можно на опубликованное объявление. Это в '
                'состоянии «%s».') % dict(
                    объявление._fields['state'].selection)[объявление.state])
        if объявление.owner_id == я:
            raise UserError(_(
                'Это ваше объявление. Откликаются на чужие.'))

        # Сторону определяет вид объявления, а не кто нажал кнопку.
        if объявление.listing_type == 'offer':
            сторона_а, сторона_б = объявление.owner_id, я
            роль_а, роль_б = _('Передаёт'), _('Принимает')
        else:
            сторона_а, сторона_б = я, объявление.owner_id
            роль_а, роль_б = _('Передаёт'), _('Принимает')

        способ = СПОСОБ.get(self.method_id.code or '', 'sale')
        # Сделку заводим через sudo: вторая сторона чужая, и права
        # заводить запись, где она стоит стороной, у откликнувшегося нет.
        # Проверки выше — вместо этих прав.
        сделка = self.env['coop.deal'].sudo().create({
            'name': объявление.name,
            'subject': 'resource',
            'way': способ,
            'party_a_id': сторона_а.id,
            'party_b_id': сторона_б.id,
            'role_a': роль_а,
            'role_b': роль_б,
            'author_id': self.env.user.partner_id.id,
            'resource_id': объявление.id,
            'city': объявление.city or '',
            'amount': self.amount or объявление.price or 0.0,
            'state': 'draft',
        })

        тело = _('Отклик на объявление «%(что)s» от %(кто)s. '
                 'Заведены переговоры по сделке %(номер)s.',
                 что=объявление.name, кто=я.display_name,
                 номер=сделка.number or '')
        if self.note:
            тело = '%s %s' % (тело, self.note)
        self.env['coop.notification']._notify(
            объявление.owner_id, тело, record=сделка, kind='deal')
        сделка.message_post(body=тело)

        # Открываем заведённую сделку: договариваются дальше в ней, а не
        # в переписке, и человек должен увидеть, куда его отклик попал.
        return {
            'type': 'ir.actions.act_window',
            'name': _('Сделка %s') % (сделка.number or ''),
            'res_model': 'coop.deal',
            'res_id': сделка.id,
            'view_mode': 'form',
            'target': 'current',
        }
