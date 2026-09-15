# -*- coding: utf-8 -*-
"""Окно участия в складчине.

В макете (`ext-group-buying.html`) на карточке складчины стоят
«Участвовать» и «Заказать». Модель заказа описана — количество, сумма,
состояние, — а завести его участник не мог: все действия раздела были
организаторскими.

Окном, а не кнопкой сразу: складчина тем и работает, что цена падает с
общим количеством, и сколько человек берёт — не мелочь, а то, от чего
зависит ступень цены для всех.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopGroupbuyJoin(models.TransientModel):
    _name = 'coop.groupbuy.join'
    _description = 'Участие в складчине'

    groupbuy_id = fields.Many2one(
        'coop.groupbuy', string='Складчина', required=True, readonly=True)
    # Валюты у складчины нет: цена ведётся ступенями, а не полем суммы.
    unit_label = fields.Char(
        related='groupbuy_id.unit_label', string='Единица', readonly=True)
    quantity = fields.Float(
        string='Сколько беру', required=True, default=1.0, digits=(16, 3))
    note = fields.Char(string='Пара слов организатору')

    def action_join(self):
        self.ensure_one()
        складчина = self.groupbuy_id
        я = self.env.user._coop_acting_partner()

        if складчина.state != 'collecting':
            raise UserError(_(
                'Участвовать можно в идущем сборе. Сейчас он в состоянии '
                '«%s».') % dict(
                    складчина._fields['state'].selection)[складчина.state])
        if складчина.organizer_id == я:
            raise UserError(_(
                'Это ваша складчина. Организатор считает себя отдельно, а не '
                'заказом наравне с участниками.'))
        if self.quantity <= 0:
            raise UserError(_('Количество должно быть больше нуля.'))

        Order = self.env['coop.groupbuy.order'].sudo()
        уже = Order.search([
            ('groupbuy_id', '=', складчина.id),
            ('partner_id', '=', я.id),
            ('state', '!=', 'cancelled'),
        ], limit=1)
        if уже:
            raise UserError(_(
                'Вы уже участвуете в этой складчине. Поправьте свой заказ, а '
                'не заводите второй.'))

        # Через sudo: заказ ссылается на чужую складчину, и права писать в
        # неё у участника нет. Проверки выше — вместо этих прав.
        заказ = Order.create({
            'groupbuy_id': складчина.id,
            'partner_id': я.id,
            'quantity': self.quantity,
            'state': 'draft',
        })

        тело = _('Заказ в складчине «%(что)s»: %(сколько)s от %(кто)s.',
                 что=складчина.name, сколько=self.quantity,
                 кто=я.display_name)
        if self.note:
            тело = '%s %s' % (тело, self.note)
        # Организатору: он ведёт сбор и без извещения о новом заказе не
        # узнает, что ступень цены сдвинулась.
        self.env['coop.notification']._notify(
            складчина.organizer_id, тело, record=складчина, kind='other')
        складчина.sudo().message_post(body=тело)
        return {'type': 'ir.actions.act_window_close'}
